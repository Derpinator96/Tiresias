"""/v1/private/query: one read-only SELECT on pg-prod for the local web app's data questions.
check() is a unit test; the endpoint tests need the seeded stack (tools container, after make seed)."""
import os
import socket

import pytest

from gateway import private_query as pq


@pytest.mark.parametrize("sql", [
    "DELETE FROM sales",
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE sales",
    "UPDATE products SET name = 'x'",
    "SELECT * INTO copy FROM sales",
    "SELECT * FROM sales FOR UPDATE",
    "WITH d AS (DELETE FROM sales RETURNING *) SELECT * FROM d",
    "CREATE TABLE x (a int)",
    "not sql at all (",
])
def test_check_rejects_anything_but_one_plain_select(sql):
    with pytest.raises(pq.Rejected):
        pq.check(sql)


def test_check_accepts_a_select_with_a_cte():
    out = pq.check("WITH t AS (SELECT product_id, SUM(quantity) q FROM sales GROUP BY 1) SELECT * FROM t ORDER BY q DESC LIMIT 5")
    assert out.upper().startswith("WITH")


@pytest.fixture(scope="module")
def client():
    if "PROD_DSN" not in os.environ:
        pytest.skip("needs the seeded stack (PROD_DSN)")
    import psycopg
    try:
        psycopg.connect(os.environ["PROD_DSN"], connect_timeout=3).close()
    except psycopg.Error as e:
        pytest.skip(f"pg-prod unreachable: {e}")
    from fastapi.testclient import TestClient
    from gateway import api

    class G:
        prod_dsn = os.environ["PROD_DSN"]
    api.gw = lambda: G
    with TestClient(api.app) as c:
        yield c


def test_top_product_query_returns_rows(client):
    r = client.post("/v1/private/query", json={"sql":
        "SELECT p.name, SUM(s.quantity) AS units FROM sales s JOIN products p ON p.product_id = s.product_id "
        "GROUP BY p.name ORDER BY units DESC LIMIT 3"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["columns"] == ["name", "units"] and len(out["rows"]) == 3 and out["truncated"] is False
    assert out["rows"][0][1] >= out["rows"][1][1]


def test_rows_are_capped(client):
    from common.config import cfg
    out = client.post("/v1/private/query", json={"sql": "SELECT product_id FROM products"}).json()
    assert len(out["rows"]) == cfg("gateway.private_query_max_rows") and out["truncated"] is True


def test_writes_are_refused_with_400(client):
    assert client.post("/v1/private/query", json={"sql": "DELETE FROM sales"}).status_code == 400


def test_session_is_read_only_and_not_superuser(client):
    out = client.post("/v1/private/query", json={"sql":
        "SELECT current_setting('transaction_read_only'), current_user, current_setting('statement_timeout')"}).json()
    from common.config import cfg
    assert out["rows"][0] == ["on", cfg("workload.app_role"), f"{cfg('gateway.private_query_timeout_s')}s"]


def test_query_refuses_the_ai_container():
    from fastapi.testclient import TestClient
    from gateway import api
    try:
        ai_ip = socket.gethostbyname("ai")
    except OSError:
        pytest.skip("no ai service on this network")
    with TestClient(api.app, client=(ai_ip, 50000)) as c:
        assert c.post("/v1/private/query", json={"sql": "SELECT 1"}).status_code == 403
