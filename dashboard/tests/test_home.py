"""Ask page tests (home.py). The gateway and ai are faked, so these need no services and no LLM
quota; the background job runs inline. The live path was checked by hand in the browser."""
import os

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from dashboard import data

HOME = os.path.join(os.path.dirname(__file__), "..", "home.py")
NAMES = {"t_aaaaaaaa": "sales", "c_00000001": "region_id", "c_00000002": "transaction_date",
         "q_00000001": 'query "SELECT SUM(amount) FROM sales ..."'}
CONFIG = {"config_id": "cfg_00000001", "search": "q_learning",
          "actions": [{"type": "add_index", "table": "t_aaaaaaaa", "columns": ["c_00000001", "c_00000002"]}]}
SIM = {"config_id": "cfg_00000001", "source": "twin", "runs": 5, "storage_mb_delta": 6.8, "write_ms_delta": 0.01,
       "templates": [{"template_id": "q_00000001", "before_ms": 40.0, "after_ms": 2.0, "speedup_pct": 95.0}]}
MIGRATION = ("-- Blind Tuner migration for cfg_00000001 (search: q_learning).\n-- Run with: psql ...\n"
             "-- 1. add_index on sales (region_id, transaction_date)\n"
             'CREATE INDEX CONCURRENTLY "bt_sales_region_id_transaction_date" ON "sales" ("region_id", "transaction_date");\n')
ROLLBACK = ("-- Blind Tuner rollback for cfg_00000001: undoes migration.sql, last action first.\n"
            "-- undo 1: drop the index migration.sql created\n"
            'DROP INDEX CONCURRENTLY IF EXISTS "bt_sales_region_id_transaction_date";\n')
ANSWER = {"question_id": "qn_00000001", "text": "The scan on t_aaaaaaaa is the bottleneck; index (c_00000001, c_00000002) cuts it.",
          "numbers": []}


def fake_services(monkeypatch, ask_status=200):
    calls = []

    def gateway(path, body=None, method=None):
        calls.append(path)
        return {"/v1/ask/resolve": {"question_id": "qn_00000001", "template_ids": ["q_00000001"]},
                "/v1/simulate/twin": SIM,
                "/v1/approve": {"files": {"migration.sql": MIGRATION, "rollback.sql": ROLLBACK, "post_deploy_check.py": ""}},
                "/v1/meta/tables": [{"table": "t_aaaaaaaa", "rows": 10000000, "size_mb": 950, "writes_per_s": 0}],
                "/v1/ledger": {"outbound_payloads": 3, "outbound_canary_hits": 0},
                }[path]

    def ai(path, body=None, method=None):
        calls.append(path)
        if path == "/ai/ask":
            if ask_status != 200:
                return httpx.Response(ask_status, json={"detail": {"error": "rate limited", "detail": "LLM API returned HTTP 429 on all 5 attempts", "events": ["x"]}})
            return httpx.Response(200, json={"status": "ok", "answer": ANSWER, "unmatched": [], "tool_calls": [],
                                             "events": [], "config": CONFIG, "simulation": SIM})
        if path == "/ai/rl/run":
            return httpx.Response(200, json={"config": CONFIG})
        if path.endswith("/events"):
            return httpx.Response(200, json={"events": []})
        raise AssertionError(path)

    def dehash(text):
        for code, name in NAMES.items():
            text = text.replace(code, name)
        return text

    monkeypatch.setattr(data, "gateway", gateway)
    monkeypatch.setattr(data, "ai", ai)
    monkeypatch.setattr(data, "dehash", dehash)
    monkeypatch.setattr(data, "estimator_label", lambda: data.LABELS["estimator"])
    # Run the background job inline, so the next run shows its finished result.
    monkeypatch.setattr(data, "start_background", lambda fn, *args: fn(*args))
    return calls


def ask(monkeypatch, **kw):
    calls = fake_services(monkeypatch, **kw)
    at = AppTest.from_file(HOME, default_timeout=30)
    at.run()
    at.button[0].click().run()          # Ask
    at.run()                            # the fragment renders the finished job
    assert not at.exception, at.exception
    return at, calls


def page_text(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption] + [s.value for s in at.subheader]
                     + [str(e.value) for e in at.error] + [c.value for c in at.code])


def test_before_asking_the_page_holds_only_the_question_and_labels(monkeypatch):
    fake_services(monkeypatch)
    at = AppTest.from_file(HOME, default_timeout=30)
    at.run()
    assert [t.value for t in at.title] == ["Blind Tuner"]
    assert len(at.text_input) == 1 and at.button[0].label == "Ask"
    text = page_text(at)
    for removed in ("Slow query templates", "Plan tree", "Workload drift", "Twin fidelity", "Resolved locally"):
        assert removed not in text
    assert data.LABELS["search"] in text and data.LABELS["twin"] in text      # required labels stay


def test_answer_time_saved_and_sql(monkeypatch):
    at, calls = ask(monkeypatch)
    text = page_text(at)
    assert "The scan on sales is the bottleneck; index (region_id, transaction_date) cuts it." in text
    m = at.metric[0]
    assert m.value == "38.0 ms" and "95% faster (40.0 to 2.0 ms)" in m.delta
    assert "10,000,000-row" in text and "median of 5 runs" in text
    apply_sql, rollback_sql = (c.value for c in at.code)
    assert apply_sql == 'CREATE INDEX CONCURRENTLY "bt_sales_region_id_transaction_date" ON "sales" ("region_id", "transaction_date");'
    assert rollback_sql == 'DROP INDEX CONCURRENTLY IF EXISTS "bt_sales_region_id_transaction_date";'
    assert "/ai/rl/run" not in calls and "/v1/simulate/twin" not in calls     # the answer's own config and measurement


def test_ai_view_hides_sql_and_names(monkeypatch):
    calls = fake_services(monkeypatch)
    at = AppTest.from_file(HOME, default_timeout=30)
    at.run()
    at.toggle[0].set_value(True).run()
    at.button[0].click().run()
    at.run()
    text = page_text(at)
    assert not at.code and "region_id" not in text and "c_00000001" in text


def test_llm_failure_still_shows_time_saved_and_sql(monkeypatch):
    at, calls = ask(monkeypatch, ask_status=503)
    assert at.error[0].value == "The LLM did not answer: LLM API returned HTTP 429 on all 5 attempts"
    assert "/ai/rl/run" in calls and "/v1/simulate/twin" in calls
    assert len(at.code) == 2 and at.metric[0].value == "38.0 ms"


def test_a_failed_step_is_shown_not_left_waiting(monkeypatch):
    fake_services(monkeypatch, ask_status=503)
    monkeypatch.setattr(data, "ai", lambda path, body=None, method=None: httpx.Response(500, text="Internal Server Error"))
    at = AppTest.from_file(HOME, default_timeout=30)
    at.run()
    at.button[0].click().run()
    at.run()
    assert any("Could not measure or write the SQL" in e.value for e in at.error)


def test_sql_statements_strip_comments_and_keep_rewrites():
    assert data.sql_statements(MIGRATION) == ('CREATE INDEX CONCURRENTLY "bt_sales_region_id_transaction_date" ON "sales" '
                                              '("region_id", "transaction_date");')
    rewrite = ("-- 2. rewrite r1 of template q_1: a suggested application code change, not run by this file.\n"
               "--    Original (latest logged query):\n--      SELECT 1\n--    Rewritten:\n--      SELECT 2\n--      FROM t\n")
    assert data.sql_statements(rewrite) == "-- rewritten query (application code change)\nSELECT 2\nFROM t"


def test_query_labels_keep_dollar_placeholders(monkeypatch):
    """Two templates in the result: each metric is labelled with its query, $n kept literal."""
    two = {**SIM, "templates": SIM["templates"] + [{"template_id": "q_00000002", "before_ms": 10.0, "after_ms": 5.0}]}
    calls = fake_services(monkeypatch)
    real_ai = data.ai

    def ai(path, body=None, method=None):
        r = real_ai(path, body, method)
        if path == "/ai/ask":
            return httpx.Response(200, json={**r.json(), "simulation": two})
        return r
    monkeypatch.setattr(data, "ai", ai)
    real_gw = data.gateway
    monkeypatch.setattr(data, "gateway", lambda path, body=None, method=None: (
        {"question_id": "qn_00000001", "template_ids": ["q_00000001", "q_00000002"]} if path == "/v1/ask/resolve"
        else real_gw(path, body, method)))
    NAMES["q_00000002"] = 'query "SELECT SUM(amount) FROM sales WHERE region_id = $1"'
    try:
        at = AppTest.from_file(HOME, default_timeout=30)
        at.run()
        at.button[0].click().run()
        at.run()
        labels = [m.label for m in at.metric]
        assert any("\$1" in l for l in labels), labels
    finally:
        del NAMES["q_00000002"]
