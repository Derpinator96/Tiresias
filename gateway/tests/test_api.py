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


# ---- rewrites (step 22) ------------------------------------------------------------------------
def _template_with(client, rule):
    cands = client.get("/v1/rewrite/candidates").json()
    return [c for c in cands if c["rule_id"] == rule]


def test_rewrite_candidates_offer_q2_and_the_or_query(client):
    trunc = _template_with(client, "date_trunc_eq_to_range")
    ors = _template_with(client, "or_same_column_to_in")
    assert trunc and ors
    for c in trunc + ors:
        assert "'" not in c["sql"] and c["label"]          # values stay as ?, never literals


def test_q2_rewrite_is_tested_only_because_verieql_cannot_encode_date_trunc(client):
    c = _template_with(client, "date_trunc_eq_to_range")[0]
    rw = client.post("/v1/rewrite/verify", json={"template_id": c["template_id"], "rule_id": c["rule_id"]}).json()
    assert errors("Rewrite", rw) == []
    assert rw["checks"] == {"verieql": "unsupported", "checksum": "match"} and rw["status"] == "TestedOnly"


def test_or_rewrite_is_verified(client):
    c = _template_with(client, "or_same_column_to_in")[0]
    rw = client.post("/v1/rewrite/verify", json={"template_id": c["template_id"], "rule_id": c["rule_id"]}).json()
    assert rw["checks"] == {"verieql": "pass", "checksum": "match"} and rw["status"] == "Verified"


def test_rule_that_does_not_fit_is_refused(client):
    c = _template_with(client, "date_trunc_eq_to_range")[0]
    r = client.post("/v1/rewrite/verify", json={"template_id": c["template_id"], "rule_id": "or_same_column_to_in"})
    assert r.status_code == 409


# ---- rewrite plus index (step 23) -------------------------------------------------------------
def test_rewrite_candidate_carries_the_rewritten_column_roles(client, codes):
    # date_trunc(transaction_date) gives the column no role in Q2; after the rewrite it is a
    # range, so the miner (AI side) can propose an index on it. Codes and roles only.
    c = _template_with(client, "date_trunc_eq_to_range")[0]
    assert {"table": codes["t"], "col": codes["td"], "role": "RANGE"} in c["columns"]
    assert_clean(c)


def test_rewrite_plus_index_is_scored_on_the_rewritten_query(client, codes):
    """HypoPG and the twin both run the rewritten Q2 when the config holds its rewrite."""
    tid = _template_with(client, "date_trunc_eq_to_range")[0]["template_id"]
    rw = {"type": "rewrite", "template_id": tid, "rule_id": "date_trunc_eq_to_range"}
    idx = {"type": "add_index", "table": codes["t"], "columns": [client.g.hasher.column("sales", "store_id"), codes["td"]]}

    def q2_cost(actions):
        out = client.post("/v1/simulate/hypopg", json={"config_id": "cfg_0000000a", "search": "q_learning",
                                                       "actions": actions}).json()
        plan = next(p for p in out["plans"] if p["template_id"] == tid)
        return next(n["est_cost"] for n in plan["nodes"] if n["parent_id"] is None)
    both = q2_cost([rw, idx])
    assert both < q2_cost([idx]) and both < q2_cost([rw])
    r = client.post("/v1/simulate/twin", json={"config_id": "cfg_0000000b", "search": "q_learning", "actions": [rw, idx]})
    assert r.status_code == 200, r.text
    t = next(x for x in r.json()["templates"] if x["template_id"] == tid)
    assert 1 - t["after_ms"] / t["before_ms"] > cfg("tests.q2_min_twin_speedup"), t


def test_twin_fidelity_is_null_or_free_of_names_and_canaries(client):
    # Private read for the dashboard, but reachable on the boundary network, so it must hold
    # no real name: the fidelity file stores query IDs, rule IDs and timings only.
    r = client.get("/v1/twin/fidelity")
    assert r.status_code == 200
    if r.json() is not None:
        assert_clean(r.json())
        assert {q["query"] for q in r.json()["queries"]} >= {"q1", "q2"}


def test_drift_windows_send_only_codes_and_shares(client, q1):
    from db import workload
    w = client.g.windows
    w.sample(now=100.0)
    with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
        conn.execute(workload.q1_sql()).fetchall()
    w.sample(now=199.0)                                    # the window [100, 200) ends at this sample
    w.sample(now=201.0)                                    # a sample past 200 closes it
    before = len(client.g.ledger.entries())
    body = client.get("/v1/workload/windows?window_s=100").json()
    assert body["window_s"] == 100 and [x["end"] for x in body["windows"]] == [200]
    assert body["windows"][0]["templates"] == {q1["template_id"]: {"time_share": 1.0, "call_share": 1.0}}
    assert_clean(body)
    assert len(client.g.ledger.entries()) == before + 1       # scanned and ledgered like every AI payload
    assert client.get("/v1/workload/windows?window_s=0").status_code == 400


# ---- payload bodies for the adversarial leak test (step 27) ----------------------------------
def test_ledger_payloads_returns_the_window_hashed_and_not_itself(client):
    from datetime import datetime, timezone
    since = datetime.now(timezone.utc)
    client.get("/v1/meta/tables")
    window = {"since": since.isoformat(), "until": datetime.now(timezone.utc).isoformat()}
    got = client.get("/v1/ledger/payloads", params=window).json()["payloads"]
    assert [p["destination"] for p in got] == ["ai"]
    assert_clean(json.loads(got[0]["body"]))
    # The bundle above was ledgered as a payload to ai, but its bytes were not kept.
    wider = {"since": since.isoformat(), "until": datetime.now(timezone.utc).isoformat()}
    assert client.get("/v1/ledger/payloads", params=wider).json()["payloads"] == got
    assert client.get("/v1/ledger/payloads", params={"since": "yesterday", "until": "now"}).status_code == 400
    naive = {"since": "2026-10-03T00:00:00", "until": "2026-10-03T01:00:00"}
    assert client.get("/v1/ledger/payloads", params=naive).status_code == 400
