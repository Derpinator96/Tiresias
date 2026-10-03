"""LLM agent tests that need no API key: the number checker, the Gemini adapter against a
mock transport (outbound scan, 429 backoff), and the tool loop with a scripted model.
The live Gemini run is in test_live_llm.py."""
import json

import httpx
import pytest

from agent import agent as agent_mod
from agent import llm, number_checker
from agent.tools import Toolbox
from contracts.validate import errors

RESULTS = {
    "tc_0000000a": {"templates": [{"before_ms": 24.297, "after_ms": 2.662, "speedup_pct": 89.0}], "storage_mb_delta": 6.8},
    "tc_0000000b": {"nodes": [{"self_ms": 27.019}], "est_rows": 2400},
}


# ---- number checker -----------------------------------------------------------------------
def test_checker_passes_tagged_numbers_with_rounding():
    text = ("The scan on t_54083dac takes 27.0 ms [tc_0000000b]. An index on (c_59811941, c_4da6361d) "
            "measured 24.3 ms [tc_0000000a] before and 2.66 ms [tc_0000000a] after, 89 % [tc_0000000a] faster, "
            "using 6.8 MB [tc_0000000a].")
    ok, unmatched, numbers = number_checker.check(text, RESULTS)
    assert ok, unmatched
    assert {"value": 2.66, "tool_call_id": "tc_0000000a"} in numbers


def test_checker_blocks_a_planted_fake_number():
    ok, unmatched, _ = number_checker.check("It will be 85% faster [tc_0000000a].", RESULTS)
    assert not ok and unmatched == ["85"]


def test_checker_blocks_untagged_numbers():
    ok, unmatched, _ = number_checker.check("It saves 21 ms.", RESULTS)
    assert not ok and unmatched == ["21"]


def test_checker_blocks_number_cited_to_wrong_call():
    ok, unmatched, _ = number_checker.check("Before: 24.3 ms [tc_0000000b].", RESULTS)
    assert not ok


def test_checker_ignores_code_digits():
    ok, unmatched, numbers = number_checker.check("Index on c_59811941 of t_54083dac for q_23387862 via cfg_751d8617.", RESULTS)
    assert ok and numbers == []


def test_strip_tags():
    assert number_checker.strip_tags("2.66 ms [tc_0000000a] after") == "2.66 ms after"


# ---- Gemini adapter -----------------------------------------------------------------------
def gemini_ok(text="done"):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


@pytest.fixture
def outbound(monkeypatch):
    sent = []

    def post(path, body):
        assert path == "/v1/ledger/outbound"
        sent.append(body)
        verdict = "block" if "CANARY" in body["body"] else "allow"
        return {"payload_id": "pay_00000001", "verdict": verdict, "canary_hits": []}
    monkeypatch.setattr(llm.gw, "post", post)
    return sent


def test_adapter_scans_the_exact_bytes_it_sends(outbound):
    seen = []

    def handler(req):
        seen.append(req.content.decode())
        return httpx.Response(200, json=gemini_ok())
    g = llm.GeminiREST("gemini-3.8-flash", "k", httpx.MockTransport(handler), sleep=lambda s: None)
    g.generate("sys", [{"role": "user", "parts": [{"text": "q_00000001"}]}], [])
    assert seen == [outbound[0]["body"]]
    assert json.loads(seen[0])["generationConfig"]["temperature"] == 0


def test_adapter_never_sends_a_blocked_body(outbound):
    calls = []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json=gemini_ok())), sleep=lambda s: None)
    with pytest.raises(llm.OutboundBlocked):
        g.generate("sys", [{"role": "user", "parts": [{"text": "CANARY_ASK_7731"}]}], [])
    assert calls == []


def test_adapter_backs_off_on_429_and_reports_it(outbound):
    replies = iter([httpx.Response(429), httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json=gemini_ok())])
    waits, events = [], []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: next(replies)), sleep=waits.append)
    g.generate("sys", [], [], on_event=events.append)
    assert waits == [2.0, 7.0]                       # initial backoff, then Retry-After
    assert all(e.startswith("rate limited, retrying") for e in events) and len(events) == 2


def test_adapter_retries_service_unavailable(outbound):
    replies = iter([httpx.Response(503), httpx.Response(200, json=gemini_ok())])
    events = []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: next(replies)), sleep=lambda s: None)
    assert g.generate("sys", [], [], on_event=events.append) == gemini_ok()
    assert events == ["LLM service unavailable (HTTP 503), retrying in 2 s (attempt 2 of 5)"]


def test_adapter_does_not_retry_client_errors(outbound):
    calls = []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(400)), sleep=lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        g.generate("sys", [], [])
    assert len(calls) == 1


def test_adapter_gives_up_after_max_attempts(outbound):
    events = []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: httpx.Response(429)), sleep=lambda s: None)
    with pytest.raises(llm.RateLimited):
        g.generate("sys", [], [], on_event=events.append)
    assert events[-1].startswith("rate limited, gave up")


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(llm.MissingKey):
        llm.provider()


# ---- agent loop with a scripted model -----------------------------------------------------
class ScriptedLLM:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []

    def generate(self, system, contents, declarations, on_event=lambda _: None):
        self.requests.append(json.loads(json.dumps(contents)))
        turn = self.turns.pop(0)
        return {"candidates": [{"content": turn(contents) if callable(turn) else turn}]}


class FakeTools(Toolbox):
    def get_slow_templates(self):
        return [{"template_id": "q_00000001", "mean_ms": 24.297}]


def call(name, args=None, cid="call-1"):
    return {"role": "model", "parts": [{"functionCall": {"id": cid, "name": name, "args": args or {}}}]}


def answer_citing_last_tool(contents):
    tc = contents[-1]["parts"][0]["functionResponse"]["response"]["tool_call_id"]
    return {"role": "model", "parts": [{"text": f"Template q_00000001 averages 24.3 ms [{tc}]."}]}


def test_loop_runs_tool_then_answers_with_checked_numbers():
    model = ScriptedLLM([call("get_slow_templates"), answer_citing_last_tool])
    r = agent_mod.ask("qn_00000001", ["q_00000001"], model, FakeTools())
    assert r.status == "ok" and errors("Answer", r.answer) == []
    assert r.answer["text"] == "Template q_00000001 averages 24.3 ms."
    fr = model.requests[1][-1]["parts"][0]["functionResponse"]
    assert fr["id"] == "call-1" and fr["name"] == "get_slow_templates"


def test_question_text_never_reaches_the_model():
    model = ScriptedLLM([{"role": "model", "parts": [{"text": "No numbers here."}]}])
    agent_mod.ask("qn_00000001", ["q_00000001"], model, FakeTools())
    first = json.dumps(model.requests[0])
    assert "weekly sales" not in first and "q_00000001" in first


def test_tool_call_cap(monkeypatch):
    from common import config
    monkeypatch.setattr(agent_mod, "cfg", lambda k: 2 if k == "llm.max_tool_calls" else config.cfg(k))
    model = ScriptedLLM([call("get_slow_templates")] * 3 + [{"role": "model", "parts": [{"text": "Stopping."}]}])
    tools = FakeTools()
    r = agent_mod.ask("qn_00000001", [], model, tools)
    assert len(tools.calls) == 2 and r.status == "ok"
    last = model.requests[-1][-1]["parts"][0]["functionResponse"]["response"]
    assert "limit" in last["result"]["error"]


def test_invented_number_retried_once_then_blocked():
    bad = {"role": "model", "parts": [{"text": "This is 85% faster."}]}
    model = ScriptedLLM([bad, bad])
    r = agent_mod.ask("qn_00000001", [], model, FakeTools())
    assert r.status == "blocked_by_checker" and r.answer is None and r.unmatched == ["85"]
    assert "do not appear" in model.requests[1][-1]["parts"][0]["text"]


def test_retry_can_recover():
    model = ScriptedLLM([call("get_slow_templates"), {"role": "model", "parts": [{"text": "About 25 ms."}]}, answer_citing_last_tool_after_feedback])
    r = agent_mod.ask("qn_00000001", [], model, FakeTools())
    assert r.status == "ok"


def answer_citing_last_tool_after_feedback(contents):
    tc = next(p["functionResponse"]["response"]["tool_call_id"] for c in contents for p in c.get("parts", []) if "functionResponse" in p)
    return {"role": "model", "parts": [{"text": f"It averages 24.297 ms [{tc}]."}]}


# ---- gnn_explain -------------------------------------------------------------------------------
EXPLAIN_PLAN = {"plan_id": "p_0000beef", "template_id": "q_00000001", "setup_id": "s_baseline", "source": "auto_explain",
                "nodes": [{"node_id": 0, "parent_id": None, "op": "Aggregate", "est_rows": 1, "est_cost": 17000,
                           "width": 8, "actual_rows": 1, "self_ms": 1.0},
                          {"node_id": 1, "parent_id": 0, "op": "Seq Scan", "relation": "t_0123abcd", "est_rows": 200,
                           "est_cost": 16000, "width": 10, "actual_rows": 80000, "self_ms": 23.0}]}


class ExplainTools(FakeTools):
    def get_plan(self, template_id):
        return EXPLAIN_PLAN


def test_gnn_explain_flags_misestimate_and_top_node():
    out = ExplainTools().gnn_explain("q_00000001")
    assert out["top_nodes"][0]["op"] == "Seq Scan"
    assert [m["node_id"] for m in out["misestimates"]] == [1] and out["misestimates"][0]["ratio"] == 400.0
    assert out["estimator"] in ("postgres_cost_calibrated", "gnn") and out["label"]


def test_gnn_explain_numbers_pass_the_checker():
    def cite(contents):
        resp = contents[-1]["parts"][0]["functionResponse"]["response"]
        pct = resp["result"]["top_nodes"][0]["predicted_share_pct"]
        return {"role": "model", "parts": [{"text": f"The scan takes {pct}% [{resp['tool_call_id']}] of predicted time."}]}
    model = ScriptedLLM([call("gnn_explain", {"template_id": "q_00000001"}), cite])
    r = agent_mod.ask("qn_00000001", ["q_00000001"], model, ExplainTools())
    assert r.status == "ok", r



def test_all_eight_doc_tools_are_declared():
    from agent.tools import DECLARATIONS
    assert {d["name"] for d in DECLARATIONS} == {"get_slow_templates", "get_plan", "mine_candidates", "run_rl",
                                                 "simulate", "gnn_explain", "rewrite_candidates", "verify"}


def test_adapter_waits_the_retry_delay_in_a_gemini_429_body_and_names_the_quota(outbound):
    err = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaMetric": "m", "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}}
    waits = []
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: httpx.Response(429, json=err)), sleep=waits.append)
    with pytest.raises(llm.RateLimited, match="quota: GenerateRequestsPerMinutePerProjectPerModel-FreeTier"):
        g.generate("sys", [], [])
    from common.config import cfg
    assert waits == [min(21.0, cfg("llm.retry_max_backoff_s"))] * (cfg("llm.retry_max_attempts") - 1)


def test_toolbox_keeps_the_config_and_simulation_behind_the_answer(monkeypatch):
    """/ai/ask returns these, so the dashboard shows the numbers the answer is about."""
    from types import SimpleNamespace
    from rl import search
    config = {"config_id": "cfg_00000001", "search": "q_learning",
              "actions": [{"type": "add_index", "table": "t_00000001", "columns": ["c_00000001"]}]}
    trace = SimpleNamespace(final_choice="best", baseline_ms=40.0, final_ms=2.0, greedy={})
    sim = {"config_id": "cfg_00000001", "source": "twin", "runs": 5, "storage_mb_delta": 1.0, "write_ms_delta": None,
           "templates": [{"template_id": "q_00000001", "before_ms": 40.0, "after_ms": 2.0}]}
    monkeypatch.setattr(search, "run", lambda *a, **k: (config, trace))
    monkeypatch.setattr(search, "twin", lambda c: (sim, None))
    tools = Toolbox()
    assert tools.last_config is None and tools.last_simulation is None
    tools.call("run_rl", {})
    assert tools.last_config == config and tools.last_simulation is None
    tools.call("simulate", {"config_id": "cfg_00000001"})
    assert tools.last_simulation["templates"][0]["speedup_pct"] == 95.0
    assert "speedup_pct" not in sim["templates"][0]          # the cached measurement is not changed
