"""Gateway component tests against the seeded pg-prod and its auto_explain log.

Run in the tools container after `make seed`. The tests use their own random HMAC key, so
the real key in .env is never needed (or read) here.
"""
import json
import os
import re
import secrets

import psycopg
import pytest
from fastapi.testclient import TestClient

from common.config import cfg
from contracts.validate import errors
from db import canaries, run_q1
from gateway.canary_scan import Scanner

REAL_NAMES = ["regions", "stores", "customers", "products", "sales", "returns", "region_id", "store_id",
              "customer_id", "product_id", "order_id", "transaction_date", "amount", "email", "full_name",
              "phone", "city", "segment", "payment_method", "unit_price", "quickmart", "2026-09-26"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["BT_HMAC_KEY"] = secrets.token_hex(cfg("gateway.hmac_key_bytes"))
    from gateway import api
    from gateway.service import Gateway
    api.gw.cache_clear()
    g = Gateway(os.environ["PROD_DSN"], os.environ["PGLOG_DIR"], str(tmp_path_factory.mktemp("ledger") / "ledger.jsonl"))
    api.gw = lambda: g                       # one gateway (and ledger) for the module
    api.gw.cache_clear = lambda: None
    with TestClient(api.app) as c:
        c.g = g
        yield c


@pytest.fixture(scope="module")
def codes(client):
    h = client.g.hasher
    return {"t": h.table("sales"), "rg": h.column("sales", "region_id"), "td": h.column("sales", "transaction_date"),
            "am": h.column("sales", "amount")}


@pytest.fixture(scope="module")
def q1(client, codes):
    slow = client.get("/v1/templates/slow").json()
    expected = f"SELECT SUM({codes['am']}) FROM {codes['t']} WHERE {codes['rg']} = ? AND {codes['td']} >= ?"
    match = [t for t in slow if t["sql"] == expected]
    assert match, f"Q1 not among slow templates: {[t['sql'] for t in slow]}"
    return match[0]


def assert_clean(payload):
    text = json.dumps(payload)
    assert Scanner().scan(text) == [], "canary in payload"
    low = text.lower()
    for name in REAL_NAMES:
        assert not re.search(rf"\b{re.escape(name)}\b", low), f"real name {name!r} in payload"


def test_slow_templates_validate_and_are_clean(client, q1):
    slow = client.get("/v1/templates/slow").json()
    for t in slow:
        assert errors("HashedQuery", t) == []
        assert t["mean_ms"] >= cfg("workload.slow_query_ms")
    assert_clean(slow)


def test_q1_template_fields(q1, codes):
    assert q1["calls"] >= cfg("workload.q1_runs")
    assert {"table": codes["t"], "col": codes["rg"], "role": "EQ"} in q1["columns"]
    assert {"table": codes["t"], "col": codes["td"], "role": "RANGE"} in q1["columns"]


def test_q1_plan_from_auto_explain(client, q1, codes):
    plans = client.get(f"/v1/templates/{q1['template_id']}/plans").json()
    assert plans
    for p in plans:
        assert errors("HashedPlan", p) == []
    assert_clean(plans)
    scan = [n for n in plans[0]["nodes"] if n["op"] == "Seq Scan"]
    assert scan and scan[0]["relation"] == codes["t"]
    # filter_cols follows the order of Postgres's filter text, which the planner may reorder.
    assert set(scan[0]["filter_cols"]) == {codes["rg"], codes["td"]}
    assert scan[0]["rows_removed"] > scan[0]["actual_rows"] > 0
    # The scan is the bottleneck: it holds the largest self time.
    assert max(plans[0]["nodes"], key=lambda n: n["self_ms"])["op"] == "Seq Scan"


def test_unknown_template_is_404(client):
    assert client.get("/v1/templates/q_00000000/plans").status_code == 404


def test_column_meta(client, codes):
    cols = client.get("/v1/meta/columns").json()
    for c in cols:
        assert errors("ColumnMeta", c) == []
    assert_clean(cols)
    rg = next(c for c in cols if c["col"] == codes["rg"])
    assert rg["n_distinct"] == cfg("dataset.regions_rows")
    assert rg["type_class"] == "id" and rg["bits"]["fk"] and rg["bits"]["eq"] and not rg["bits"]["indexed"]
    # Skew sums the top 5 frequencies: region 7 alone holds about 30%.
    assert rg["skew"] > cfg("dataset.hero_region_share")
    td = next(c for c in cols if c["col"] == codes["td"])
    assert td["type_class"] == "date" and td["bits"]["range"]


def test_table_meta(client, codes):
    tables = client.get("/v1/meta/tables").json()
    for t in tables:
        assert errors("TableMeta", t) == []
    sales = next(t for t in tables if t["table"] == codes["t"])
    assert sales["rows"] == cfg("dataset.sales_rows")
    assert sales["size_mb"] > 0


def test_unparsable_query_is_withheld(client):
    with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
        conn.execute("SELECT 1 AS withheld_probe").fetchall()
    snap = client.g.snapshot()
    assert snap.withheld >= 1
    assert all("withheld_probe" not in json.dumps(t.hashed) for t in snap.templates)


def test_resolver_maps_question_without_sending_it(client, q1):
    question = f"Why is the weekly sales dashboard timing out? {canaries.QUESTION.value}"
    before = len(client.g.ledger.entries())
    r = client.post("/v1/ask/resolve", json={"question": question}).json()
    assert r["template_ids"][0] == q1["template_id"]
    assert re.fullmatch(r"qn_[0-9a-f]{8}", r["question_id"])
    assert r["question_had_canary"] is True
    assert len(client.g.ledger.entries()) == before    # nothing was sent anywhere


def test_dehash(client, codes, q1):
    answer = {"question_id": "qn_00000001",
              "text": f"Index ({codes['rg']}, {codes['td']}) on {codes['t']} for {q1['template_id']}.",
              "numbers": []}
    text = client.post("/v1/answers/dehash", json=answer).json()["text"]
    assert text.startswith("Index (region_id, transaction_date) on sales for query \"SELECT SUM(amount) FROM sales")


def test_outbound_scan_allows_clean_and_blocks_canary(client, codes):
    ok = client.post("/v1/ledger/outbound", json={"destination": "llm", "body": json.dumps({"q": codes["t"]})}).json()
    bad = client.post("/v1/ledger/outbound", json={"destination": "llm", "body": "find CANARY_7731@corp.com"}).json()
    assert ok["verdict"] == "allow" and bad["verdict"] == "block"
    assert errors("LedgerEntry", ok) == [] and errors("LedgerEntry", bad) == []


def test_negative_control_lights_up(client):
    entry = client.post("/v1/privacy/negative-control").json()
    assert entry["destination"] == "local_scanner"
    found = {h["canary_id"] for h in entry["canary_hits"]}
    assert {c.canary_id for c in canaries.COMMENTS} <= found


def test_ledger_counts_outbound_separately(client):
    led = client.get("/v1/ledger").json()
    assert led["outbound_payloads"] >= 1
    # The only outbound payload with hits is the deliberate canary in the outbound test above.
    # It was blocked. One payload can hold several hits: the planted emails share fragments.
    hit_entries = [e for e in led["entries"] if e["destination"] in ("ai", "llm") and e["canary_hits"]]
    assert led["outbound_blocked"] == len(hit_entries) == 1
    assert hit_entries[0]["verdict"] == "block"
    assert led["control_canary_hits"] >= 2


def test_pending_endpoints_say_which_step(client, codes):
    cfg_obj = {"config_id": "cfg_00000001", "search": "greedy",
               "actions": [{"type": "add_index", "table": codes["t"], "columns": [codes["rg"], codes["td"]]}]}
    # Twin simulation (step 10) and checksum (step 12) are built. Still not built: rewrite
    # equivalence and approve, both out of scope this session.
    r = client.post("/v1/twin/checksum", json={"config": cfg_obj, "rewritten_sql": "SELECT ?"})
    assert r.status_code == 501 and "out of scope" in r.json()["detail"]
    r = client.post("/v1/approve")
    assert r.status_code == 501 and "out of scope" in r.json()["detail"]
