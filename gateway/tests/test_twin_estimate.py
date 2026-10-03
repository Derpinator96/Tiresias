"""Twin estimate in recorded mode (human decision 2026-10-04): the ratio and clamp math, plus
one component test against the seeded pg-prod (tools container, after `make seed`)."""
import os
import secrets

import pytest

from common.config import cfg
from contracts.validate import errors
from gateway.service import estimate_after_ms


def test_ratio_scales_before_ms():
    assert estimate_after_ms(200.0, 1000.0, 250.0, 0.1) == 50.0


def test_ratio_is_clamped_to_min_and_one():
    assert estimate_after_ms(200.0, 1000.0, 1.0, 0.1) == pytest.approx(20.0)      # floor
    assert estimate_after_ms(200.0, 1000.0, 5000.0, 0.1) == 200.0                 # never slower
    assert estimate_after_ms(200.0, 0.0, 5000.0, 0.1) == 200.0                    # zero cost: unchanged


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    if "PROD_DSN" not in os.environ:
        pytest.skip("needs the seeded stack (PROD_DSN)")
    import psycopg
    try:
        psycopg.connect(os.environ["PROD_DSN"], connect_timeout=3).close()
    except psycopg.Error as e:
        pytest.skip(f"pg-prod unreachable: {e}")
    from fastapi.testclient import TestClient
    os.environ["BT_HMAC_KEY"] = secrets.token_hex(cfg("gateway.hmac_key_bytes"))
    from gateway import api
    from gateway.service import Gateway
    api.gw.cache_clear()
    g = Gateway(os.environ["PROD_DSN"], os.environ["PGLOG_DIR"], str(tmp_path_factory.mktemp("ledger") / "ledger.jsonl"))
    api.gw = lambda: g
    api.gw.cache_clear = lambda: None
    with TestClient(api.app) as c:
        c.g = g
        yield c


def test_q1_index_is_estimated_when_not_recorded(client, monkeypatch):
    from gateway import api
    monkeypatch.setattr(api, "cfg", lambda k: "recorded" if k == "sandbox.twin_mode" else cfg(k))
    monkeypatch.setattr(api, "_twin_records", lambda: {})          # force the estimate path
    h = client.g.hasher
    t, rg, td, am = h.table("sales"), h.column("sales", "region_id"), h.column("sales", "transaction_date"), h.column("sales", "amount")
    q1_sql = f"SELECT SUM({am}) FROM {t} WHERE {rg} = ? AND {td} >= ?"
    slow = client.get("/v1/templates/slow").json()
    q1 = next((x for x in slow if x["sql"] == q1_sql), None)
    assert q1, "Q1 not among slow templates"
    config = {"config_id": "cfg_0000000e", "search": "q_learning",
              "actions": [{"type": "add_index", "table": t, "columns": [rg, td]}]}
    r = client.post("/v1/simulate/twin", json=config)
    assert r.status_code == 200, r.text
    sim = r.json()
    assert errors("SimResult", sim) == []
    assert sim["source"] == "twin" and sim["runs"] == cfg("sandbox.timing_runs")
    row = next(x for x in sim["templates"] if x["template_id"] == q1["template_id"])
    assert row["before_ms"] == q1["mean_ms"]
    assert row["after_ms"] < row["before_ms"], row
    assert row["after_ms"] >= row["before_ms"] * cfg("sandbox.estimate_min_ratio")
    assert sim["write_ms_delta"] == pytest.approx(cfg("rl.write_penalty_ms_per_index"))
    assert sim["storage_mb_delta"] > 0
