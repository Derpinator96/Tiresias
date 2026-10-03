"""Plan generation component tests against pg-bench (bench container, after
`make plans-load`). Fails, never skips, if BENCH_DSN is missing."""
import os

import psycopg

from common.config import cfg
from db.plangen import load, quickmart_templates, run, setups


def test_bench_dsn_present():
    assert os.environ.get("BENCH_DSN"), "run in the bench container: make test-plangen"


def _indexes(database):
    with psycopg.connect(load.dsn_for(database)) as conn:
        return conn.execute("""SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid
                               WHERE c.relnamespace = 'public'::regnamespace AND NOT i.indisprimary""").fetchone()[0]


def test_apply_setup_replaces_indexes():
    run.apply_setup("quickmart", setups.QUICKMART["s_qm_fk"])
    assert _indexes("quickmart") == len(setups.QUICKMART["s_qm_fk"])
    run.apply_setup("quickmart", setups.QUICKMART["s_qm_base"])
    assert _indexes("quickmart") == 0


def test_run_one_records_analyzed_plan():
    tid, demo, sqls = quickmart_templates.instances(1, 1, load.quickmart_databases()["quickmart"])[0]
    rec = run.run_one(("quickmart", tid, demo, 0, "s_qm_base", sqls[0]))
    assert rec["error"] is None and not rec["timed_out"]
    assert rec["runtime_ms"] > 0 and rec["shape_hash"]
    root = rec["plan"]["Plan"]
    assert "Actual Total Time" in root and "Total Cost" in root   # actual and estimated in one plan


def test_timeout_keeps_estimated_plan():
    seconds = int(cfg("postgres.statement_timeout_plan_generation_s")) + 1
    rec = run.run_one(("quickmart", "test/sleep", False, 0, "s_qm_base", f"SELECT pg_sleep({seconds})"))
    assert rec["timed_out"] and rec["runtime_ms"] is None and rec["error"] is None
    assert "Actual Total Time" not in rec["plan"]["Plan"]
