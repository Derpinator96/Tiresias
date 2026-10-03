"""Approve tests: the post-deploy check's logic (unit), the generated files (sqlglot, real
names), migration then rollback on the twin, and the generated check script run as a real
subprocess against pg-twin. Component tests need make seed. Nothing here changes pg-prod except
a small index on regions that one test creates and drops.
"""
import json
import os
import socket
import secrets
import subprocess
import sys

import psycopg
import pytest
import sqlglot
from fastapi.testclient import TestClient
from sqlglot import exp

from common.config import cfg
from gateway import post_deploy_check as pdc

FILES = {"migration.sql", "rollback.sql", "post_deploy_check.py"}


# ---- unit: the check's decision -------------------------------------------------------------
def test_worse_flags_only_templates_over_the_threshold():
    before = {"q_a": 100.0, "q_b": 100.0, "q_c": 100.0}
    assert pdc.worse(before, dict(before), 0.10) == {}                       # unchanged
    assert pdc.worse(before, {"q_a": 100.0, "q_b": 105.0, "q_c": 120.0}, 0.10) == {"q_c": pytest.approx(0.20)}


def test_statements_skip_comments_and_join_lines():
    text = "-- a\nCREATE INDEX CONCURRENTLY x ON t (a);\n\n-- b ; c\nDROP INDEX\n  CONCURRENTLY y;\n-- only a comment\n"
    assert pdc.statements(text) == ["CREATE INDEX CONCURRENTLY x ON t (a);", "DROP INDEX\n  CONCURRENTLY y;"]


class FakeConn:
    def __init__(self):
        self.ran = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        self.ran.append(statement)


@pytest.mark.parametrize("after_ms,rolled_back", [(100.0, False), (109.0, False), (150.0, True)])
def test_check_runs_rollback_only_when_median_is_worse(tmp_path, monkeypatch, after_ms, rolled_back):
    conn = FakeConn()
    monkeypatch.setattr(pdc, "HERE", tmp_path)
    monkeypatch.setattr(pdc.psycopg, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pdc, "replay", lambda c, q, s, w=0: {"q_a": {"median_ms": after_ms, "runs": 5}})
    monkeypatch.setitem(pdc.PARAMS, "worse_by", 0.10)
    (tmp_path / "rollback.sql").write_text('-- undo 1\nDROP INDEX CONCURRENTLY IF EXISTS "bt_x";\n')
    (tmp_path / "post_deploy_baseline.json").write_text(json.dumps({"q_a": {"median_ms": 100.0, "runs": 5}}))
    report = pdc.main(["check", "--minutes", "0"])
    assert report["rolled_back"] is rolled_back
    assert conn.ran == (['DROP INDEX CONCURRENTLY IF EXISTS "bt_x";'] if rolled_back else [])


# ---- component -------------------------------------------------------------------------------
TWIN = os.environ.get("TWIN_DSN", "")
PROD = os.environ.get("PROD_DSN", "")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["BT_HMAC_KEY"] = secrets.token_hex(cfg("gateway.hmac_key_bytes"))
    from gateway import api
    from gateway.service import Gateway
    g = Gateway(PROD, os.environ["PGLOG_DIR"], str(tmp_path_factory.mktemp("ledger") / "ledger.jsonl"))
    api.gw = lambda: g
    with TestClient(api.app) as c:
        c.g = g
        yield c


@pytest.fixture(scope="module")
def codes(client):
    h = client.g.hasher
    return {"t": h.table("sales"), "rg": h.column("sales", "region_id"), "td": h.column("sales", "transaction_date"),
            "am": h.column("sales", "amount"), "pm": h.column("sales", "payment_method")}


@pytest.fixture(scope="module")
def q1_id(client, codes):
    expected = f"SELECT SUM({codes['am']}) FROM {codes['t']} WHERE {codes['rg']} = ? AND {codes['td']} >= ?"
    return next(t["template_id"] for t in client.get("/v1/templates/slow").json() if t["sql"] == expected)


def index_config(codes, *cols):
    return {"config_id": "cfg_0000a001", "search": "q_learning",
            "actions": [{"type": "add_index", "table": codes["t"], "columns": [codes[c] for c in cols]}]}


def run(dsn, *statements):
    with psycopg.connect(dsn, autocommit=True) as conn:
        for s in statements:
            conn.execute(s)


def run_file(dsn, text):
    with psycopg.connect(dsn, autocommit=True) as conn:
        pdc.run_sql(conn, text)


def indexes(dsn):
    with psycopg.connect(dsn, autocommit=True) as conn:
        return conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1").fetchall()


def parsed(text):
    """Statements sqlglot finds. It returns trailing comments as a bare Semicolon; skip those."""
    return [s for s in sqlglot.parse(text, read="postgres") if s is not None and not isinstance(s, exp.Semicolon)]


def test_files_parse_and_name_real_tables_and_columns(client, codes, q1_id):
    q2 = next(c for c in client.get("/v1/rewrite/candidates").json() if c["rule_id"] == "date_trunc_eq_to_range")
    config = index_config(codes, "rg", "td")
    config["actions"] += [{"type": "rewrite", "template_id": q2["template_id"], "rule_id": q2["rule_id"]},
                          {"type": "partition", "table": codes["t"], "column": codes["td"], "scheme": "range_month"}]
    ledgered = len(client.g.ledger.entries())
    r = client.post("/v1/approve", json=config)
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert set(files) == FILES
    assert len(client.g.ledger.entries()) == ledgered                  # private: never ledgered

    [create] = parsed(files["migration.sql"])                          # rewrite and partition are comments
    assert isinstance(create, exp.Create) and "CONCURRENTLY" in create.sql(dialect="postgres")
    assert create.find(exp.Table).name == "sales"
    assert [c.name for c in create.find_all(exp.Column)] == ["region_id", "transaction_date"]
    assert len(pdc.statements(files["migration.sql"])) == 1
    assert "date_trunc" in files["migration.sql"]                     # original, as a comment
    assert f"transaction_date >= '{cfg('workload.q2_month')}'" in files["migration.sql"]   # rewritten
    assert "PARTITION BY RANGE (\"transaction_date\")" in files["migration.sql"]

    [drop] = parsed(files["rollback.sql"])
    assert isinstance(drop, exp.Drop) and drop.args["concurrently"] and drop.args["exists"]
    assert drop.find(exp.Table).name == create.this.name               # drops exactly what migration made

    ns = {"__name__": "generated", "__file__": "/tmp/post_deploy_check.py"}
    exec(compile(files["post_deploy_check.py"], "post_deploy_check.py", "exec"), ns)
    params = ns["PARAMS"]
    assert params["minutes"] == cfg("approve.post_deploy_check_minutes")
    assert params["worse_by"] == cfg("approve.rollback_if_median_worse_by")
    assert "FROM sales" in params["queries"][q1_id] and f"region_id = {cfg('dataset.hero_region_id')}" in params["queries"][q1_id]


def test_unknown_code_and_constraint_index_are_refused(client, codes):
    bad = index_config(codes, "rg")
    bad["actions"][0]["table"] = "t_00000000"
    assert client.post("/v1/approve", json=bad).status_code == 400
    pkey = {"config_id": "cfg_0000a002", "search": "greedy",
            "actions": [{"type": "drop_index", "index": client.g.hasher.index("sales_pkey")}]}
    r = client.post("/v1/approve", json=pkey)
    assert r.status_code == 400 and "constraint" in r.json()["detail"]


def test_add_index_migration_then_rollback_leaves_twin_indexes_unchanged(client, codes):
    files = client.post("/v1/approve", json=index_config(codes, "rg", "td")).json()["files"]
    before = indexes(TWIN)
    try:
        run_file(TWIN, files["migration.sql"])
        assert len(indexes(TWIN)) == len(before) + 1
    finally:
        run_file(TWIN, files["rollback.sql"])
    assert indexes(TWIN) == before


def test_drop_index_rollback_recreates_its_definition(client):
    name = "bt_test_regions_region_name"
    for dsn in (PROD, TWIN):
        run(dsn, f"CREATE INDEX {name} ON regions (region_name)")
    try:
        config = {"config_id": "cfg_0000a003", "search": "greedy",
                  "actions": [{"type": "drop_index", "index": client.g.hasher.index(name)}]}
        r = client.post("/v1/approve", json=config)
        assert r.status_code == 200, r.text
        files = r.json()["files"]
        [drop] = parsed(files["migration.sql"])
        assert isinstance(drop, exp.Drop) and drop.args["concurrently"] and drop.find(exp.Table).name == name
        [create] = parsed(files["rollback.sql"])
        assert create.find(exp.Table).name == "regions" and [c.name for c in create.find_all(exp.Column)] == ["region_name"]
        before = indexes(TWIN)
        run_file(TWIN, files["migration.sql"])
        assert name not in {n for n, _ in indexes(TWIN)}
        run_file(TWIN, files["rollback.sql"])
        assert indexes(TWIN) == before
    finally:
        for dsn in (PROD, TWIN):
            run(dsn, f"DROP INDEX IF EXISTS {name}")


def test_check_script_rolls_back_on_the_twin_when_latency_gets_worse(client, codes, q1_id, tmp_path):
    """Baseline with a helper index that serves Q1, then migration.sql (an index that does not
    help Q1), then the helper is dropped: Q1 gets slower, so the script must run rollback.sql."""
    from db.sandbox import twin_measure
    from gateway import approve
    mapping = twin_measure.load_map()
    files = approve.build(client.g, client.g.snapshot(), index_config(codes, "pm"),
                          lambda s: twin_measure.map_query(s, mapping))
    for name, text in files.items():
        (tmp_path / name).write_text(text)

    def phase(name):
        out = subprocess.run([sys.executable, str(tmp_path / "post_deploy_check.py"), name, "--minutes", "0.05"],
                             env={**os.environ, "BT_DSN": TWIN}, capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    original = indexes(TWIN)
    try:
        run(TWIN, "CREATE INDEX bt_test_helper ON sales (region_id, transaction_date)")
        phase("baseline")
        run_file(TWIN, files["migration.sql"])
        run(TWIN, "DROP INDEX bt_test_helper")
        report = phase("check")
        assert report["rolled_back"] is True and q1_id in report["worse"]
        assert indexes(TWIN) == original                                # the script ran rollback.sql
    finally:
        run(TWIN, "DROP INDEX IF EXISTS bt_test_helper")
        run_file(TWIN, files["rollback.sql"])


def test_twin_check_endpoint_measures_and_restores_the_twin(client, codes, q1_id):
    before = indexes(TWIN)
    r = client.post("/v1/approve/twin-check", json=index_config(codes, "rg", "td"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ran_on"] == "twin" and out["minutes"] == cfg("approve.demo_check_minutes")
    # The index serves Q1, so Q1's median drops. Other replayed templates on sales may move with
    # machine noise, so whether the whole check rolled back is not asserted, only its consistency.
    assert out["templates"][q1_id]["median_ms"] < out["baseline"][q1_id]["median_ms"]
    assert out["rolled_back"] == bool(out["worse"])
    assert indexes(TWIN) == before


def test_approve_refuses_the_ai_container(codes):
    from gateway import api
    ai_ip = socket.gethostbyname("ai")       # tools shares the boundary network with ai
    with TestClient(api.app, client=(ai_ip, 50000)) as c:
        assert c.post("/v1/approve", json=index_config(codes, "rg", "td")).status_code == 403
        assert c.post("/v1/approve/twin-check", json=index_config(codes, "rg", "td")).status_code == 403


def test_dashboard_label_matches_the_owning_module():
    from dashboard.data import LABELS
    from gateway import approve
    assert LABELS["approve_demo"] == approve.LABEL
