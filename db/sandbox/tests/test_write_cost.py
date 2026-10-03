"""Write cost (db/sandbox/write_cost.py). The parser test needs no database; the component test
runs against the seeded pg-prod and pg-twin (tools container)."""
import os

import psycopg

from dashboard import data
from db import workload
from db.sandbox import twin_measure, write_cost

# Lines of a real `pgbench -l -R` log from pg-twin (pgbench 16.15, 2026-10-03): client_id
# transaction_no time script_no time_epoch time_us schedule_lag, in microseconds.
LOG = """0 0 2471 0 1791023092 561340 87
0 1 1455 0 1791023092 561598 1231
0 2 536 0 1791023092 580374 68""".splitlines()


def test_median_subtracts_schedule_lag():
    # 2471 - 87 = 2384, 1455 - 1231 = 224, 536 - 68 = 468: median 468 us.
    assert write_cost.median_ms(LOG) == 0.468


def test_dashboard_label_matches_the_module():
    assert data.LABELS["write_cost"] == write_cost.LABEL


def twin_state(conn):
    rows = conn.execute("SELECT count(*), max(order_id) FROM sales").fetchone()
    indexes = conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1").fetchall()
    return rows, indexes


def test_index_on_sales_adds_write_cost_and_twin_is_left_as_it_was():
    with psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as twin:
        start = twin_state(twin)
        r = twin_measure.measure(os.environ["PROD_DSN"], os.environ["TWIN_DSN"],
                                 [("sales", ["region_id", "transaction_date"])], {"q1": workload.q1_sql()})
        assert twin_state(twin) == start
    assert r.write_ms_delta > 0
