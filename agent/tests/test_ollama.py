"""Ollama adapter (air-gapped mode) against a mock transport: tool-call and answer parsing,
the malformed-reply retry, the ledger before every send, the context-size guard, and the
unchanged tool loop and number checker driven through it. No Ollama is needed."""
import json

import httpx
import pytest

from agent import agent as agent_mod
from agent import llm
from agent.tests.test_agent import FakeTools, outbound  # noqa: F401  (outbound is a fixture)
from agent.tools import DECLARATIONS
from common.config import cfg


def chat(content, **extra):
    return httpx.Response(200, json={"model": "gemma2:2b", "message": {"role": "assistant", "content": content},
                                     "done": True, "done_reason": "stop", "prompt_eval_count": 100, "eval_count": 20, **extra})


def model(replies, seen=None):
    replies = iter(replies)

    def handler(req):
        if seen is not None:
            seen.append(json.loads(req.content))
        return next(replies)
    return llm.OllamaChat("gemma2:2b", "http://ollama.test:11434", httpx.MockTransport(handler), sleep=lambda s: None)


USER = [{"role": "user", "parts": [{"text": "Question qn_00000001. Templates: q_00000001."}]}]


def test_tool_call_reply_becomes_a_function_call(outbound):
    seen = []
    m = model([chat('{"name": "get_plan", "args": {"template_id": "q_00000001"}, "answer": ""}')], seen)
    out = m.generate("sys", USER, DECLARATIONS)
    assert out["candidates"][0]["content"]["parts"] == [{"functionCall": {"name": "get_plan", "args": {"template_id": "q_00000001"}}}]
    req = seen[0]
    assert req["stream"] is False and req["model"] == "gemma2:2b"
    assert req["options"] == {"temperature": 0, "num_ctx": cfg("llm.ollama.num_ctx"), "num_predict": cfg("llm.ollama.num_predict")}
    assert set(req["format"]["properties"]["name"]["enum"]) == {d["name"] for d in DECLARATIONS} | {llm.FINAL}
    assert req["messages"][0]["role"] == "system" and "get_plan" in req["messages"][0]["content"]


def test_final_answer_reply_becomes_text(outbound):
    m = model([chat('{"name": "final_answer", "args": {}, "answer": "Done."}')])
    assert m.generate("sys", USER, DECLARATIONS)["candidates"][0]["content"]["parts"] == [{"text": "Done."}]


def test_tool_results_go_back_as_user_messages_with_their_id():
    contents = USER + [{"role": "model", "parts": [{"functionCall": {"name": "get_slow_templates", "args": {}}}]},
                       {"role": "user", "parts": [{"functionResponse": {"name": "get_slow_templates", "response": {
                           "tool_call_id": "tc_0000000a", "result": [{"mean_ms": 24.297}]}}}]}]
    msgs = llm.ollama_messages(contents)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]   # gemma2's template drops a "tool" role
    assert msgs[2]["content"] == 'Result of tc_0000000a (get_slow_templates): [{"mean_ms":24.297}]'


def test_malformed_reply_is_retried_with_feedback(outbound):
    seen, events = [], []
    m = model([chat('{"name": "get_pl'), chat('{"name": "final_answer", "args": {}, "answer": "Done."}')], seen)
    out = m.generate("sys", USER, DECLARATIONS, on_event=events.append)
    assert out["candidates"][0]["content"]["parts"] == [{"text": "Done."}]
    assert seen[1]["messages"][-2] == {"role": "assistant", "content": '{"name": "get_pl'}
    assert "not one JSON object" in seen[1]["messages"][-1]["content"]
    assert any("not one valid JSON" in e for e in events)


def test_malformed_reply_fails_after_the_retries(outbound):
    bad = [chat("not json"), chat('{"name": "drop_table", "args": {}, "answer": ""}')]
    with pytest.raises(llm.MalformedReply):
        model(bad).generate("sys", USER, DECLARATIONS)


def test_every_body_is_ledgered_before_it_is_sent(outbound):
    ledgered_at_send = []

    def handler(req):   # what the ledger held at the moment these bytes went out
        ledgered_at_send.append([o["body"] for o in outbound] == [req.content.decode()])
        return chat('{"name": "final_answer", "args": {}, "answer": "Done."}')
    m = llm.OllamaChat("gemma2:2b", "http://ollama.test:11434", httpx.MockTransport(handler))
    m.generate("sys", USER, DECLARATIONS)
    assert ledgered_at_send == [True] and outbound[0]["destination"] == "llm"


def test_blocked_body_is_never_sent(outbound):
    calls = []
    m = llm.OllamaChat("gemma2:2b", "http://ollama.test:11434", httpx.MockTransport(lambda r: calls.append(r) or chat("{}")))
    with pytest.raises(llm.OutboundBlocked):
        m.generate("sys", [{"role": "user", "parts": [{"text": "CANARY_ASK_7731"}]}], DECLARATIONS)
    assert calls == []


def test_context_guard_refuses_before_ledger_or_send(outbound):
    calls = []
    m = llm.OllamaChat("gemma2:2b", "http://ollama.test:11434", httpx.MockTransport(lambda r: calls.append(r) or chat("{}")))
    huge = [{"role": "user", "parts": [{"text": "1" * cfg("llm.ollama.num_ctx")}]}]   # digits: one token each
    with pytest.raises(llm.ContextOverflow, match="not sent"):
        m.generate("sys", huge, DECLARATIONS)
    assert calls == [] and outbound == []


def test_context_guard_also_trips_when_ollama_reports_a_full_context(outbound):
    m = model([chat('{"name": "final_answer", "args": {}, "answer": "Done."}', prompt_eval_count=cfg("llm.ollama.num_ctx"))])
    with pytest.raises(llm.ContextOverflow):
        m.generate("sys", USER, DECLARATIONS)


def test_estimate_counts_each_digit_as_a_token():
    assert llm.estimate_tokens("1234") == 4
    assert llm.estimate_tokens("ab" * 5) == int(10 / cfg("llm.ollama.chars_per_token"))


def test_agent_loop_unchanged_through_ollama(outbound):
    """Tool call, then an answer citing the tool's ID: the same loop and checker as Gemini."""
    def handler(req):
        msgs = json.loads(req.content)["messages"]
        results = [m["content"] for m in msgs if m["content"].startswith("Result of tc_")]
        if not results:
            return chat('{"name": "get_slow_templates", "args": {}, "answer": ""}')
        tc = results[0].split()[2]
        return chat(json.dumps({"name": "final_answer", "args": {}, "answer": f"Template q_00000001 averages 24.3 ms [{tc}]."}))
    m = llm.OllamaChat("gemma2:2b", "http://ollama.test:11434", httpx.MockTransport(handler))
    r = agent_mod.ask("qn_00000001", ["q_00000001"], m, FakeTools())
    assert r.status == "ok" and r.answer["text"] == "Template q_00000001 averages 24.3 ms."
    assert [c["name"] for c in r.tool_calls] == ["get_slow_templates"] and len(outbound) == 2


def test_provider_switch_needs_no_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("BT_LLM_PROVIDER", "ollama")
    p = llm.provider()
    assert isinstance(p, llm.OllamaChat) and p.model == cfg("llm.ollama.model")
    assert p.url == cfg("llm.ollama.base_url").rstrip("/") + "/api/chat"


def test_label_names_the_local_model_and_the_checked_route(monkeypatch):
    monkeypatch.setenv("BT_LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "llm_api_reachable", lambda: False)
    assert llm.label() == llm.LABEL_OLLAMA.format(model=cfg("llm.ollama.model"), route=llm.ROUTE_NONE)
    monkeypatch.setattr(llm, "llm_api_reachable", lambda: True)
    assert "NOT air-gapped" in llm.label()
    monkeypatch.delenv("BT_LLM_PROVIDER")
    assert llm.label() == llm.LABEL_GEMINI.format(model=cfg("llm.model"))
