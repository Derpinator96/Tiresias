"""HypoPG what-if tests against the seeded pg-prod (tools container), plus the gateway
endpoint that wraps it."""
import os

import httpx
import psycopg

from contracts.validate import errors
from db import workload
from db.sandbox import hypopg


def test_hypothetical_index_changes_q1_plan_and_reports_size():
    q1 = workload.q1_sql()
    base = hypopg.explain_with_indexes(os.environ["PROD_DSN"], [], {"q": (q1, False)})
    hypo = hypopg.explain_with_indexes(os.environ["PROD_DSN"], [("sales", ["region_id", "transaction_date"])], {"q": (q1, False)})
    assert base.index_bytes == 0 and hypo.index_bytes > 0
    assert hypo.plans["q"]["Plan"]["Total Cost"] < base.plans["q"]["Plan"]["Total Cost"]
    assert "hypo" not in str(base.plans["q"]).lower()
    assert "btree_sales_region_id_transaction_date" in str(hypo.plans["q"])


def test_generic_plan_for_placeholder_query():
    sql = "SELECT SUM(amount) FROM sales WHERE region_id = $1 AND transaction_date >= $2"
    out = hypopg.explain_with_indexes(os.environ["PROD_DSN"], [], {"q": (sql, True)})
    assert out.plans["q"]["Plan"]["Node Type"] == "Aggregate"


def test_nothing_real_is_built():
    hypopg.explain_with_indexes(os.environ["PROD_DSN"], [("sales", ["region_id"])], {})
    with psycopg.connect(os.environ["PROD_DSN"]) as conn:
        n = conn.execute("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname NOT LIKE '%%_pkey'").fetchone()[0]
    assert n == 0


def test_gateway_endpoint_returns_estimated_hashed_plans():
    base = os.environ["GATEWAY_URL"]
    from miner.fpgrowth import candidates
    templates = httpx.get(base + "/v1/templates/slow", timeout=30).json()
    meta = httpx.get(base + "/v1/meta/columns", timeout=30).json()
    top = [c for c in candidates(templates, meta) if len(c["columns"]) == 2][0]
    config = {"config_id": "cfg_0000abcd", "search": "greedy",
              "actions": [{"type": "add_index", "table": top["table"], "columns": top["columns"]}]}
    out = httpx.post(base + "/v1/simulate/hypopg", json=config, timeout=60).json()
    assert out["index_storage_mb"] > 0
    for p in out["plans"]:
        assert errors("HashedPlan", p) == []
        assert p["source"] == "hypopg" and p["setup_id"] == "s_cfg_0000abcd"
        assert all("self_ms" not in n and "actual_rows" not in n for n in p["nodes"])
    ops = {n["op"] for n in out["plans"][0]["nodes"]}
    assert ops & {"Index Scan", "Bitmap Index Scan", "Index Only Scan"}


def test_gateway_rejects_unknown_codes():
    config = {"config_id": "cfg_0000abce", "search": "greedy",
              "actions": [{"type": "add_index", "table": "t_00000000", "columns": ["c_00000000"]}]}
    r = httpx.post(os.environ["GATEWAY_URL"] + "/v1/simulate/hypopg", json=config, timeout=30)
    assert r.status_code == 400
