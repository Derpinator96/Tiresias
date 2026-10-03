"""Gateway unit tests: hashing, literal and comment stripping, plan filters, rounding,
canary scanning and the ledger. No database needed."""
import json
import re

import pytest

from contracts.validate import errors
from db import canaries
from gateway.canary_scan import Scanner
from gateway.hashing import Hasher
from gateway.ledger import Ledger
from gateway.rounding import round_count, round_sig
from gateway.strip import Unparsed, hash_filter, hash_sql

KEY_A = bytes(range(32))
KEY_B = bytes(range(1, 33))
SCHEMA = {
    "sales": {"order_id", "customer_id", "product_id", "store_id", "region_id", "transaction_date", "quantity", "amount", "payment_method"},
    "stores": {"store_id", "region_id", "city", "opened_on"},
    "customers": {"customer_id", "email", "full_name", "phone", "city", "signup_date", "segment"},
}
REAL_WORDS = re.compile(r"sales|stores|customers|region_id|transaction_date|amount|email|segment|retail|2026|\b7\b", re.I)


@pytest.fixture
def h():
    return Hasher(KEY_A)


# ---- hashing ------------------------------------------------------------------------------
def test_codes_are_prefix_plus_8_hex(h):
    assert re.fullmatch(r"t_[0-9a-f]{8}", h.table("sales"))
    assert re.fullmatch(r"c_[0-9a-f]{8}", h.column("sales", "region_id"))


def test_same_name_same_code_and_key_changes_code(h):
    assert h.table("sales") == Hasher(KEY_A).table("sales")
    assert h.table("sales") != Hasher(KEY_B).table("sales")


def test_table_dot_column_separates_same_column_name(h):
    assert h.column("sales", "region_id") != h.column("stores", "region_id")


def test_vault_maps_codes_back(h):
    code = h.column("sales", "region_id")
    assert h.vault[code] == {"kind": "column", "name": "sales.region_id"}


# ---- SQL stripping ------------------------------------------------------------------------
def test_q1_with_literals(h):
    sql, cols = hash_sql("SELECT SUM(amount) FROM sales WHERE region_id = 7 AND transaction_date >= '2026-09-26'", h, SCHEMA)
    t, rg, td, am = h.table("sales"), h.column("sales", "region_id"), h.column("sales", "transaction_date"), h.column("sales", "amount")
    assert sql == f"SELECT SUM({am}) FROM {t} WHERE {rg} = ? AND {td} >= ?"
    assert {(c["col"], c["role"]) for c in cols} == {(am, "SELECT"), (rg, "EQ"), (td, "RANGE")}


def test_pg_stat_statements_placeholders(h):
    sql, _ = hash_sql("SELECT SUM(amount) FROM sales WHERE region_id = $1 AND transaction_date >= $2", h, SCHEMA)
    assert "$" not in sql and sql.count("?") == 2


@pytest.mark.parametrize("raw", [
    "/* CANARY_QXZ7731_VK */ SELECT COUNT(*) FROM customers WHERE segment = 'retail'",
    "SELECT COUNT(*) FROM customers WHERE segment = 'retail' -- CANARY_QXZ7732_VK",
    "SELECT customer_id FROM customers WHERE email = 'CANARY_7731@corp.com'",
    "SELECT customer_id FROM customers WHERE email IN ('a@b.c', 'CANARY_7731@corp.com')",
])
def test_comments_and_values_never_survive(h, raw):
    sql, _ = hash_sql(raw, h, SCHEMA)
    assert not Scanner().scan(sql)
    assert not REAL_WORDS.search(sql)
    assert errors("HashedQuery", {"template_id": "q_00000000", "sql": sql, "calls": 1, "mean_ms": 1.0, "total_ms": 1.0, "columns": []}) == []


def test_aliases_resolved_and_join_role(h):
    sql, cols = hash_sql("SELECT s.amount AS total FROM sales s JOIN stores st ON st.store_id = s.store_id WHERE st.region_id = 7", h, SCHEMA)
    assert " s." not in sql and "st." not in sql and "total" not in sql
    roles = {(c["col"], c["role"]) for c in cols}
    assert (h.column("stores", "store_id"), "JOIN") in roles and (h.column("sales", "store_id"), "JOIN") in roles
    assert (h.column("stores", "region_id"), "EQ") in roles


def test_function_wrapped_column_gets_no_eq_role(h):
    _, cols = hash_sql("SELECT amount FROM sales WHERE date_trunc('month', transaction_date) = '2026-09-01'", h, SCHEMA)
    assert (h.column("sales", "transaction_date"), "EQ") not in {(c["col"], c["role"]) for c in cols}


@pytest.mark.parametrize("raw", [
    "SELECT 1",                                            # no table
    "SELECT * FROM pg_stat_statements",                    # not a QuickMart table
    'SELECT * FROM "SALES"',                               # uppercase identifier: unknown table
    "SELECT region_id FROM sales JOIN stores USING (store_id)",  # ambiguous column
    "SELECT nonexistent FROM sales",                       # unknown column
    "SELEC amount FRM sales WHERE",                        # not valid SQL
    "SELECT x.amount FROM (SELECT amount FROM sales) x",   # subquery alias would leak a name
])
def test_fail_closed(h, raw):
    with pytest.raises(Unparsed):
        hash_sql(raw, h, SCHEMA)


# ---- plan filters -------------------------------------------------------------------------
def test_plan_filter_with_cast(h):
    text, cols = hash_filter("((region_id = 7) AND (transaction_date >= '2026-09-26'::date))", h, SCHEMA, {"sales": "sales"}, "sales")
    assert cols == [h.column("sales", "region_id"), h.column("sales", "transaction_date")]
    assert "7" not in text.replace(h.column("sales", "region_id"), "").replace(h.column("sales", "transaction_date"), "")
    assert "2026" not in text and "?" in text


def test_plan_filter_with_aliases(h):
    text, _ = hash_filter("(s.store_id = st.store_id)", h, SCHEMA, {"s": "sales", "st": "stores"}, None)
    assert text == f"({h.column('sales', 'store_id')} = {h.column('stores', 'store_id')})"


@pytest.mark.parametrize("raw", ["(hashed SubPlan 1)", "(city = 'Raipur'::text) AND (unknown_col = 3)"])
def test_plan_filter_fail_closed(h, raw):
    with pytest.raises(Unparsed):
        hash_filter(raw, h, SCHEMA, {"stores": "stores"}, "stores")


# ---- rounding -----------------------------------------------------------------------------
@pytest.mark.parametrize("x,expected", [(49_812_334, 50_000_000), (1_000_000, 1_000_000), (2407, 2400), (12, 12), (0, 0)])
def test_round_count(x, expected):
    assert round_count(x) == expected


def test_round_sig_fraction():
    assert round_sig(73.4) == 73 and round_sig(0.0456) == 0.046


# ---- canary scanner -----------------------------------------------------------------------
def test_scanner_exact_case_insensitive():
    hits = Scanner().scan('{"x": "canary_7731@CORP.com"}')
    assert {"canary_id": canaries.EMAILS[0].canary_id, "match": "exact"} in hits


def test_scanner_fragment():
    # 6 characters of "Quillon Vexmarrow", nothing more.
    hits = Scanner().scan("note: vexmar")
    assert {"canary_id": canaries.NAMES[0].canary_id, "match": "fragment"} in hits


def test_scanner_hits_never_hold_values():
    hits = Scanner().scan("CANARY_7731@corp.com 7731.77 Zephyrine Kettle KX-7731")
    assert hits and all(set(h) == {"canary_id", "match"} for h in hits)
    assert "7731" not in json.dumps(hits)


def test_scanner_clean_on_hashed_payload(h):
    sql, _ = hash_sql("SELECT SUM(amount) FROM sales WHERE region_id = 7 AND transaction_date >= '2026-09-26'", h, SCHEMA)
    assert Scanner().scan(json.dumps({"sql": sql, "est_rows": 2400, "est_cost": 25000})) == []


# ---- ledger -------------------------------------------------------------------------------
def test_ledger_entry_valid_and_verdict(tmp_path):
    led = Ledger(str(tmp_path / "ledger.jsonl"))
    ok = led.record("ai", b"{}", [])
    bad = led.record("llm", b"x", [{"canary_id": canaries.QUESTION.canary_id, "match": "exact"}])
    assert ok["verdict"] == "allow" and bad["verdict"] == "block"
    assert errors("LedgerEntry", ok) == [] and errors("LedgerEntry", bad) == []
    assert [e["payload_id"] for e in led.entries()] == [ok["payload_id"], bad["payload_id"]]


def test_drift_window_shares_count_a_reset_counter_whole():
    from gateway.windows import shares
    before = {"q_0000000a": (10, 1000.0), "q_0000000b": (5, 500.0)}
    after = {"q_0000000a": (14, 1300.0), "q_0000000b": (2, 100.0), "q_0000000c": (0, 0.0)}   # b was reset
    assert shares(before, after) == {"q_0000000a": {"time_share": 0.75, "call_share": 0.6667},
                                     "q_0000000b": {"time_share": 0.25, "call_share": 0.3333}}


def test_drift_windows_are_closed_and_aligned():
    from gateway.windows import Windows
    totals = {"q_0000000a": (0, 0.0)}
    w = Windows(lambda: dict(totals))
    for t in range(95, 330, 5):                        # one call of 100 ms per 5 s
        totals["q_0000000a"] = (t // 5, t // 5 * 100.0)
        w.sample(now=float(t))
    wins = w.windows(100)
    assert [x["end"] for x in wins] == [200, 300]      # [100, 200) and [200, 300); 300 to 325 is open
    assert wins[0]["templates"] == {"q_0000000a": {"time_share": 1.0, "call_share": 1.0}}
