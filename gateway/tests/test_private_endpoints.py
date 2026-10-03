"""Private-side endpoints for the local web app (real names; refused to the ai service).
Component tests against the seeded pg-prod in the tools container, after `make seed`."""
import os
import secrets

import pytest

from common.config import cfg


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


def test_names_map_codes_to_real_names(client):
    names = client.get("/v1/private/names").json()
    assert names[client.g.hasher.table("sales")] == "sales"
    assert names[client.g.hasher.column("sales", "region_id")] == "sales.region_id"
    q = [c for c in names if c.startswith("q_")]
    assert q and all("SELECT" in names[c].upper() or "INSERT" in names[c].upper() or "UPDATE" in names[c].upper()
                     or "DELETE" in names[c].upper() for c in q)


ROW_KEYS = {"template_id", "sql", "calls", "mean_ms", "total_ms", "slow", "example"}


def test_slow_log_lists_every_template_by_total_ms(client):
    log = client.get("/v1/private/slow-log").json()
    assert log["threshold_ms"] == cfg("workload.slow_query_ms")
    rows = log["templates"]
    assert rows and all(set(r) == ROW_KEYS for r in rows)
    totals = [r["total_ms"] for r in rows]
    assert totals == sorted(totals, reverse=True)
    for r in rows:
        assert r["slow"] == (r["mean_ms"] >= log["threshold_ms"])
        assert r["example"] is None or isinstance(r["example"], str)
    assert any(r["slow"] and r["example"] for r in rows), "Q1 should be slow with a logged query"


def test_slow_log_random_is_one_entry(client):
    r = client.get("/v1/private/slow-log/random").json()
    assert set(r) == ROW_KEYS


def test_tables_with_samples(client):
    tables = client.get("/v1/private/tables?rows=3").json()
    by_name = {t["table"]: t for t in tables}
    assert "sales" in by_name
    s = by_name["sales"]
    assert s["code"] == client.g.hasher.table("sales") and s["rows"] > 0 and s["size_mb"] > 0
    assert {c["name"] for c in s["columns"]} >= {"region_id", "transaction_date", "amount"}
    assert all(c["code"] == client.g.hasher.column("sales", c["name"]) for c in s["columns"])
    assert len(s["sample"]) == 3 and all(len(row) == len(s["columns"]) for row in s["sample"])
    big = client.get(f"/v1/private/tables?rows={cfg('web.sample_rows_max') + 50}").json()
    assert len({t["table"]: t for t in big}["sales"]["sample"]) == cfg("web.sample_rows_max")
    default = client.get("/v1/private/tables").json()
    assert len({t["table"]: t for t in default}["sales"]["sample"]) == cfg("web.sample_rows")
