"""Twin tests (tools container, after make seed). The twin must hold zero real values, keep
the statistics Q1 depends on, and agree with production's plan shape."""
import json
import os

import psycopg
import pytest

from common.config import cfg
from db import canaries, workload
from db.sandbox import twin_measure
from gateway.canary_scan import Scanner


@pytest.fixture(scope="module")
def twin():
    with psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as c:
        yield c


@pytest.fixture(scope="module")
def prod():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as c:
        yield c


def text_columns(conn):
    return conn.execute("""SELECT c.table_name, c.column_name FROM information_schema.columns c
                           JOIN information_schema.tables t USING (table_schema, table_name)
                           WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                             AND c.data_type = 'text'""").fetchall()


def test_hero_table_at_full_size(twin, prod):
    n = lambda c: c.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert n(twin) == n(prod) * cfg("sandbox.twin_hero_table_scale")


def test_no_canary_in_twin_text(twin):
    scanner = Scanner()
    for table, col in text_columns(twin):
        blob = "\n".join(r[0] for r in twin.execute(f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL'))
        assert scanner.scan(blob) == [], f"{table}.{col}"


def test_no_canary_amount_reaches_twin_inputs(prod):
    # A row-level check cannot work for dense numbers: the twin draws a million amounts at cent
    # precision (about 540,000 distinct), so any given cent value, canary or not, appears by
    # chance about as often as its neighbours (measured 2026-10-03, see db/NOTES.md). What must
    # hold is that no canary amount is an input the generator copies or anchors on: the
    # frequency-rank map and the histogram bounds it samples between.
    twin_map = open(cfg("sandbox.twin_map_path"), encoding="utf-8").read()
    bounds = prod.execute("""SELECT histogram_bounds::text::text[] FROM pg_stats
                             WHERE schemaname = 'public' AND tablename = 'sales' AND attname = 'amount'""").fetchone()[0] or []
    for c in canaries.AMOUNTS:
        assert c.value not in twin_map
        assert c.value not in bounds


@pytest.mark.parametrize("table,col", [("sales", "payment_method"), ("customers", "segment"), ("customers", "city")])
def test_no_real_text_values(twin, prod, table, col):
    real = {r[0] for r in prod.execute(f"SELECT DISTINCT {col} FROM {table}")}
    synth = {r[0] for r in twin.execute(f"SELECT DISTINCT {col} FROM {table}")}
    assert not (real & synth)


def test_region_skew_and_distinct_count_kept(twin):
    rows = twin.execute("SELECT region_id, COUNT(*)::float / SUM(COUNT(*)) OVER () FROM sales GROUP BY 1 ORDER BY 2 DESC").fetchall()
    assert len(rows) == cfg("dataset.regions_rows")
    assert abs(rows[0][1] - cfg("dataset.hero_region_share")) < 0.01


def test_frequency_rank_map_and_q1_translation():
    mapping = twin_measure.load_map()
    hero = str(cfg("dataset.hero_region_id"))
    assert mapping["sales.region_id"][hero] == 1           # most common real region -> twin ID 1
    q = twin_measure.map_query(workload.q1_sql(), mapping)
    assert "region_id = 1" in q and cfg("workload.q1_since") in q   # range literal unchanged


def test_twin_map_never_mounted_in_ai():
    compose = open(os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "docker-compose.yml"), encoding="utf-8").read()
    ai_block = compose.split("\n  ai:\n", 1)[1].split("\n  dashboard:\n", 1)[0]
    assert "gateway-ledger" not in ai_block and "/var/lib/blind-tuner" not in ai_block


def test_q1_plan_agrees_and_index_speeds_it_up(twin):
    r = twin_measure.measure(os.environ["PROD_DSN"], os.environ["TWIN_DSN"],
                             [("sales", ["region_id", "transaction_date"])], {"q1": workload.q1_sql()})
    assert r.plan_agreement["q1"]
    assert r.after_ms["q1"] < r.before_ms["q1"]
    assert r.storage_mb > 0
    left = twin.execute("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'bt_sim_%%'").fetchone()[0]
    assert left == 0, "measurement must drop its indexes"
