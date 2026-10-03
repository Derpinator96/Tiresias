"""Checksum tests on the twin (tools container, after make seed)."""
import os

import psycopg
import pytest

from db import workload
from db.sandbox import checksum, twin_measure
from rl import search
from verify import checksum as verify_checksum


@pytest.fixture(scope="module")
def twin_q1():
    return twin_measure.map_query(workload.q1_sql(), twin_measure.load_map())


def test_same_query_same_checksum_different_query_different(twin_q1):
    with psycopg.connect(os.environ["TWIN_DSN"]) as conn:
        a, _ = checksum.result_md5(conn, twin_q1)
        b, _ = checksum.result_md5(conn, twin_q1)
        c, _ = checksum.result_md5(conn, twin_q1.replace("region_id = 1", "region_id = 2"))
    assert a == b and a != c


def test_checksum_ignores_row_order():
    with psycopg.connect(os.environ["TWIN_DSN"]) as conn:
        a, n = checksum.result_md5(conn, "SELECT region_id FROM regions ORDER BY region_id")
        b, _ = checksum.result_md5(conn, "SELECT region_id FROM regions ORDER BY region_id DESC")
    assert a == b and n == 12


def test_q1_index_preserves_results(twin_q1):
    r = checksum.index_preserves_results(os.environ["TWIN_DSN"], [("sales", ["region_id", "transaction_date"])], twin_q1)
    assert r["match"] and r["rows"] == 1


def test_gateway_and_verify_report_tested_only():
    from agent import gateway_client as gw
    config, _ = search.run()
    tid = gw.get("/v1/templates/slow")[0]["template_id"]
    r = verify_checksum.index_config(tid, config)
    assert r["match"] and r["status"] == "TestedOnly"
    assert r["checks"] == {"verieql": "not_run", "checksum": "match"}
