"""Twin fidelity (db/sandbox/fidelity.py). The unit test needs no database; the component test
runs in the tools container after make seed. It builds Q1's index on pg-prod for the
measurement only, so it also proves pg-prod comes back untouched: primary key indexes only, no
new template for the gateway, no new auto_explain plan."""
import os

import psycopg

from common.config import cfg
from db.sandbox import fidelity
from gateway.ingest import plans as plans_mod

PK_ONLY = """SELECT count(*) FILTER (WHERE NOT ix.indisprimary), count(*) FROM pg_index ix
             JOIN pg_class c ON c.oid = ix.indrelid WHERE c.relnamespace = 'public'::regnamespace"""
APP_STATEMENTS = """SELECT count(*), coalesce(sum(calls), 0) FROM pg_stat_statements s
                    JOIN pg_roles r ON r.oid = s.userid WHERE r.rolname = %s"""


def test_fidelity_is_twin_speedup_over_production_speedup():
    e = fidelity.entry("q2", "date_trunc_eq_to_range", 1, (900.0, 300.0), (1000.0, 250.0), True, False)
    assert e["twin"]["speedup"] == 3.0 and e["production"]["speedup"] == 4.0
    assert e["fidelity"] == 0.75
    assert e["plan_agrees"] == {"before": True, "after": False}


def test_q1_fidelity_measured_and_prod_restored():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as conn:
        indexes = conn.execute(PK_ONLY).fetchone()
        app = conn.execute(APP_STATEMENTS, (cfg("workload.app_role"),)).fetchone()
    logged = len(plans_mod.read_log(os.environ["PGLOG_DIR"]))

    e = fidelity.measure_query(os.environ["PROD_DSN"], os.environ["TWIN_DSN"], "q1", cfg("sandbox.fidelity_queries")["q1"])
    assert e["plan_agrees"] == {"before": True, "after": True}
    assert e["twin"]["speedup"] > 1 and e["production"]["speedup"] > 1 and e["fidelity"] > 0

    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as conn:
        assert conn.execute(PK_ONLY).fetchone() == indexes == (0, 6)
        assert conn.execute(APP_STATEMENTS, (cfg("workload.app_role"),)).fetchone() == app
        assert conn.execute("SELECT count(*) FROM pg_stat_statements WHERE query LIKE %s",
                            ("%bt_fidelity_%",)).fetchone()[0] == 0, "the measuring session must not be tracked"
    assert len(plans_mod.read_log(os.environ["PGLOG_DIR"])) == logged, "the measuring session must not be logged"
