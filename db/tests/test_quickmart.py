"""Step 5 tests against the seeded pg-prod (run in the tools container after `make seed`).

Checks the doc's "Data generation rules" and "Canary placement", and that Q1 reached both
pg_stat_statements and the auto_explain log.
"""
import glob
import json
import os
from datetime import date

import psycopg
import pytest

from common.config import cfg
from db import canaries, generate, workload


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as c:
        yield c


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


@pytest.mark.parametrize("table", ["regions", "stores", "products", "customers", "sales", "returns"])
def test_row_counts_match_config(conn, table):
    assert one(conn, f"SELECT COUNT(*) FROM {table}") == generate.sizes()[table]


def test_hero_region_share(conn):
    share = one(conn, "SELECT AVG((region_id = %s)::int)::float FROM sales", cfg("dataset.hero_region_id"))
    assert abs(share - cfg("dataset.hero_region_share")) < 0.01, share


def test_every_sale_carries_its_store_region(conn):
    assert one(conn, "SELECT COUNT(*) FROM sales s JOIN stores st USING (store_id) WHERE s.region_id <> st.region_id") == 0


def test_top_products_earn_most_revenue(conn):
    share = one(conn, """
        WITH r AS (SELECT product_id, SUM(amount) AS rev FROM sales GROUP BY product_id),
             ranked AS (SELECT rev, ROW_NUMBER() OVER (ORDER BY rev DESC) AS rk FROM r)
        SELECT (SUM(rev) FILTER (WHERE rk <= (SELECT COUNT(*) FROM products) * %s) / SUM(rev))::float FROM ranked
    """, cfg("dataset.top_product_share"))
    # Products are drawn for sales at top_product_revenue_share, and ranking by realised
    # revenue can only raise the share, so it must be at least the target, within noise.
    assert share >= cfg("dataset.top_product_revenue_share") - 0.02, share


def test_dates_in_range_and_denser_recently(conn):
    lo, hi = conn.execute("SELECT MIN(transaction_date), MAX(transaction_date) FROM sales").fetchone()
    assert lo >= date.fromisoformat(cfg("dataset.date_start"))
    assert hi <= date.fromisoformat(cfg("dataset.date_end"))
    first, last = conn.execute("""
        SELECT COUNT(*) FILTER (WHERE transaction_date < %s::date + 30),
               COUNT(*) FILTER (WHERE transaction_date > %s::date - 30)
        FROM sales""", (cfg("dataset.date_start"), cfg("dataset.date_end"))).fetchone()
    assert last > 2 * first, (first, last)


def test_returns_follow_sale_by_configured_days(conn):
    lo, hi = conn.execute("""SELECT MIN(r.return_date - s.transaction_date), MAX(r.return_date - s.transaction_date)
                             FROM returns r JOIN sales s USING (order_id)""").fetchone()
    assert lo >= cfg("dataset.return_lag_days_min") and hi <= cfg("dataset.return_lag_days_max"), (lo, hi)


def test_only_primary_key_indexes(conn):
    rows = conn.execute("""SELECT i.indexrelid::regclass::text, ix.indisprimary
                           FROM pg_index ix JOIN pg_class c ON c.oid = ix.indrelid
                           JOIN pg_namespace n ON n.oid = c.relnamespace
                           JOIN pg_index i ON i.indexrelid = ix.indexrelid
                           WHERE n.nspname = 'public'""").fetchall()
    assert len(rows) == 6 and all(primary for _, primary in rows), rows


def test_foreign_keys_match_the_doc(conn):
    # The doc's QuickMart table marks exactly these columns (FK).
    expected = {("stores", "region_id"), ("sales", "customer_id"), ("sales", "product_id"),
                ("sales", "store_id"), ("sales", "region_id"), ("returns", "order_id")}
    rows = conn.execute("""SELECT c.conrelid::regclass::text, a.attname
                           FROM pg_constraint c JOIN pg_attribute a
                             ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                           WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace""").fetchall()
    assert set(rows) == expected


@pytest.mark.parametrize("c", canaries.ROW_CANARIES, ids=lambda c: c.kind + ":" + c.canary_id)
def test_row_canary_planted(conn, c):
    sql = {
        "customer_email": "SELECT COUNT(*) FROM customers WHERE email = %s",
        "customer_name": "SELECT COUNT(*) FROM customers WHERE full_name = %s",
        "customer_phone": "SELECT COUNT(*) FROM customers WHERE phone = %s",
        "product_name": "SELECT COUNT(*) FROM products WHERE name = %s",
        "sale_amount": "SELECT COUNT(*) FROM sales WHERE amount = %s::numeric",
    }[c.kind]
    assert one(conn, sql, c.value) >= 1


def test_canary_placement_count():
    assert canaries.PLACEMENTS == cfg("canaries.planted_target")


def test_q1_in_pg_stat_statements(conn):
    calls = one(conn, """SELECT COALESCE(SUM(calls), 0) FROM pg_stat_statements
                         WHERE query LIKE 'SELECT SUM(amount) FROM sales WHERE region_id = $1 AND transaction_date >= $2'""")
    assert calls >= cfg("workload.q1_runs")


def test_canary_queries_in_pg_stat_statements(conn):
    texts = [r[0] for r in conn.execute("SELECT query FROM pg_stat_statements").fetchall()]
    for c in canaries.COMMENTS:
        assert any(c.value in t for t in texts), c.kind


def test_q1_slower_than_threshold(conn):
    mean = one(conn, """SELECT MAX(mean_exec_time) FROM pg_stat_statements
                        WHERE query LIKE 'SELECT SUM(amount) FROM sales WHERE region_id = $1%%'""")
    assert mean > cfg("workload.slow_query_ms"), mean


def test_q1_plan_in_auto_explain_log():
    q1 = workload.q1_sql()
    found = []
    for path in glob.glob(os.path.join(os.environ["PGLOG_DIR"], "*.json")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                msg = rec.get("message", "")
                if "plan:" in msg:
                    plan = json.loads(msg.split("plan:", 1)[1])
                    if plan.get("Query Text") == q1:
                        found.append(plan)
    assert found, "Q1 plan not in the auto_explain log"
    top = found[-1]["Plan"]
    assert top["Node Type"] == "Aggregate"
    assert "Actual Total Time" in top   # log_analyze on: real times recorded
