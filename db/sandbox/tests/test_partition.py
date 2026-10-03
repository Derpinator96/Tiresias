"""Partition measurement (db/sandbox/twin_measure.py step 6, db/sandbox/fidelity.py for Q3). The
unit tests need no database; the component test runs in the tools container after make seed. It
builds monthly partitioned copies of sales on pg-twin and on pg-prod for the measurement only,
so it also proves both come back exactly as they were."""
import os
from datetime import date

import psycopg

from common.config import cfg
from db import workload
from db.sandbox import fidelity, twin_measure
from db.sandbox.tests.test_fidelity import APP_STATEMENTS, PK_ONLY
from gateway.ingest import plans as plans_mod


def test_months_cover_the_data_with_half_open_bounds():
    assert twin_measure._months(date(2025, 11, 17), date(2026, 1, 31)) == [
        date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]
    assert twin_measure._months(date(2026, 9, 1), date(2026, 9, 1)) == [date(2026, 9, 1), date(2026, 10, 1)]


def test_retarget_points_every_reference_at_the_copy_under_the_old_name():
    q = twin_measure.retarget(workload.q3_sql(), "sales", "bt_sim_part")
    assert "FROM bt_sim_part AS sales WHERE" in q
    q2 = twin_measure.retarget(workload.q2_sql(), "sales", "bt_sim_part")
    assert "FROM bt_sim_part AS s JOIN products" in q2 and "s.transaction_date" in q2


def state(conn):
    tables = conn.execute("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace "
                          "AND relkind IN ('r', 'p') ORDER BY 1").fetchall()
    sales = conn.execute("SELECT 'sales'::regclass::oid, count(*), max(order_id) FROM sales").fetchone()
    indexes = conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1").fetchall()
    return tables, sales, indexes


def test_q3_partition_fidelity_measured_and_twin_and_prod_restored():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as prod, \
            psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as twin:
        prod_start, twin_start = state(prod), state(twin)
        pk_only = prod.execute(PK_ONLY).fetchone()
        app = prod.execute(APP_STATEMENTS, (cfg("workload.app_role"),)).fetchone()
    logged = len(plans_mod.read_log(os.environ["PGLOG_DIR"]))

    e = fidelity.measure_query(os.environ["PROD_DSN"], os.environ["TWIN_DSN"], "q3", cfg("sandbox.fidelity_queries")["q3"])
    print("\nQ3 fidelity:", e)
    assert e["partition"] is True and e["indexes"] == 0
    assert e["plan_agrees"]["before"]
    assert e["twin"]["speedup"] > 1 and e["production"]["speedup"] > 1 and e["fidelity"] > 0

    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as prod, \
            psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as twin:
        assert state(prod) == prod_start and state(twin) == twin_start
        assert prod.execute(PK_ONLY).fetchone() == pk_only == (0, 6)
        assert prod.execute(APP_STATEMENTS, (cfg("workload.app_role"),)).fetchone() == app
        assert prod.execute("SELECT count(*) FROM pg_stat_statements WHERE query LIKE %s",
                            ("%bt_fidelity_%",)).fetchone()[0] == 0, "the measuring session must not be tracked"
    assert len(plans_mod.read_log(os.environ["PGLOG_DIR"])) == logged, "the measuring session must not be logged"
