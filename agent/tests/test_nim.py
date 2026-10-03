"""NVIDIA NIM provider tests with a mock transport: no key, no network. The live run is
e2e/test_q1.py[nim]; recorded runs replay in test_llm_replay.py."""
import json

import httpx
import pytest

from agent import agent as agent_mod
from agent import llm
from agent.tools import Toolbox
from common.config import cfg
from contracts.validate import errors

DECL = [{"name": "get_slow_templates", "description": "d", "parameters": {"type": "object", "properties": {}}}]


def reply(message: dict, finish="stop") -> dict:
    return {"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": message, "finish_reason": finish}]}


@pytest.fixture
def outbound(monkeypatch):
    sent = []

    def post(path, body):
        assert path == "/v1/ledger/outbound"
        sent.append(body)
        return {"payload_id": "pay_00000001", "verdict": "block" if "CANARY" in body["body"] else "allow", "canary_hits": []}
    monkeypatch.setattr(llm.gw, "post", post)
    return sent


def nim(handler, sleep=lambda s: None, clock=None):
    kw = {"clock": clock} if clock else {}
    return llm.NimChat("nvidia/test-model", "k", httpx.MockTransport(handler), sleep=sleep, **kw)


def test_request_shape_and_exact_bytes_are_scanned(outbound):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=reply({"role": "assistant", "content": "done"}))
    nim(handler).generate("sys", [{"role": "user", "parts": [{"text": "q_00000001"}]}], DECL)
    req = seen[0]
    assert str(req.url) == cfg("llm.nim.base_url").rstrip("/") + "/chat/completions"
    assert req.headers["authorization"] == "Bearer k"
    body = json.loads(req.content)
    assert req.content.decode() == outbound[0]["body"]               # the scanned bytes are the sent bytes
    assert body["model"] == "nvidia/test-model" and body["temperature"] == 0
    assert body["max_tokens"] == cfg("llm.nim.max_tokens")
    assert body["tools"] == [{"type": "function", "function": DECL[0]}] and body["tool_choice"] == "auto"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "q_00000001"}]


def test_a_blocked_body_is_never_sent(outbound):
    calls = []
    with pytest.raises(llm.OutboundBlocked):
        nim(lambda r: calls.append(r) or httpx.Response(200, json=reply({"content": "x"}))).generate(
            "sys", [{"role": "user", "parts": [{"text": "CANARY_ASK_7731"}]}], DECL)
    assert calls == []


@pytest.mark.parametrize("status", [429, 500, 503, 504])
def test_retryable_statuses_back_off(outbound, status):
    replies = iter([httpx.Response(status), httpx.Response(200, json=reply({"role": "assistant", "content": "ok"}))])
    waits, events = [], []
    out = nim(lambda r: next(replies), sleep=waits.append).generate("sys", [], DECL, on_event=events.append)
    assert out["candidates"][0]["content"]["parts"] == [{"text": "ok"}]
    assert waits == [cfg("llm.retry_initial_backoff_s")] and len(events) == 1


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ProxyError])
def test_a_failed_connection_backs_off_and_is_scanned_once(outbound, exc):
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            raise exc("502 Bad Gateway", request=req)
        return httpx.Response(200, json=reply({"role": "assistant", "content": "ok"}))
    waits, events = [], []
    out = nim(handler, sleep=waits.append).generate("sys", [], DECL, on_event=events.append)
    assert out["candidates"][0]["content"]["parts"] == [{"text": "ok"}]
    assert len(calls) == 2 and len(outbound) == 1 and len(waits) == 1
    assert events[0].startswith("LLM host unreachable")


def test_a_connection_that_never_returns_raises_the_transport_error(outbound):
    def handler(req):
        raise httpx.ConnectError("down", request=req)
    with pytest.raises(httpx.ConnectError):
        nim(handler).generate("sys", [], DECL)


def test_a_read_timeout_is_not_retried(outbound):
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(httpx.ReadTimeout):
        nim(handler).generate("sys", [], DECL)
    assert len(calls) == 1


def test_tool_calls_become_function_calls_with_ids(outbound):
    msg = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "chatcmpl-tool-1", "type": "function", "function": {"name": "get_slow_templates", "arguments": "{}"}}]}
    out = nim(lambda r: httpx.Response(200, json=reply(msg, "tool_calls"))).generate("sys", [], DECL)
    assert out["candidates"][0]["content"]["parts"] == [
        {"functionCall": {"id": "chatcmpl-tool-1", "name": "get_slow_templates", "args": {}}}]


def test_malformed_arguments_and_unknown_tools_are_counted(outbound):
    msg = {"role": "assistant", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "get_slow_templates", "arguments": "{not json"}},
        {"id": "b", "type": "function", "function": {"name": "drop_database", "arguments": "{}"}}]}
    events = []
    p = nim(lambda r: httpx.Response(200, json=reply(msg)))
    out = p.generate("sys", [], DECL, on_event=events.append)
    assert len(p.tool_call_errors) == 2 and all(e.startswith("tool-call error") for e in events)
    assert out["candidates"][0]["content"]["parts"][0]["functionCall"]["args"] == {}


def test_think_blocks_are_not_part_of_the_answer(outbound):
    msg = {"role": "assistant", "content": "<think>numbers 42 and 7</think>The scan is the bottleneck."}
    out = nim(lambda r: httpx.Response(200, json=reply(msg))).generate("sys", [], DECL)
    assert out["candidates"][0]["content"]["parts"] == [{"text": "The scan is the bottleneck."}]


def test_requests_are_spaced_for_the_free_tier(outbound):
    now = [100.0]
    waits = []

    def sleep(s):
        waits.append(s)
        now[0] += s
    p = nim(lambda r: httpx.Response(200, json=reply({"content": "ok"})), sleep=sleep, clock=lambda: now[0])
    p.generate("sys", [], DECL)
    now[0] += 0.5
    p.generate("sys", [], DECL)
    assert waits == [pytest.approx(cfg("llm.nim.min_request_interval_s") - 0.5)]


def test_missing_key_or_model_refuses_to_start(monkeypatch):
    monkeypatch.delenv(cfg("llm.nim.api_key_env"), raising=False)
    with pytest.raises(llm.MissingKey, match="NVIDIA_API_KEY"):
        llm.provider(name="nim")
    monkeypatch.setenv(cfg("llm.nim.api_key_env"), "k")
    if not cfg("llm.nim.model"):
        with pytest.raises(llm.MissingKey, match="llm-bench"):
            llm.provider(name="nim")
    assert isinstance(llm.provider(name="nim", model="nvidia/x"), llm.NimChat)


def test_agent_loop_round_trips_tool_call_ids_as_tool_messages(outbound):
    """Full loop: NIM asks for a tool, gets its result as a role "tool" message with the same
    tool_call_id, then answers with a tagged number that passes the checker."""
    bodies = []

    class Tools(Toolbox):
        def get_slow_templates(self):
            return [{"template_id": "q_00000001", "mean_ms": 24.297}]

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(200, json=reply({"role": "assistant", "content": None, "tool_calls": [
                {"id": "call-7", "type": "function", "function": {"name": "get_slow_templates", "arguments": "{}"}}]}))
        tc = json.loads(body["messages"][-1]["content"])["tool_call_id"]
        return httpx.Response(200, json=reply({"role": "assistant", "content": f"It averages 24.3 ms [{tc}]."}))
    r = agent_mod.ask("qn_00000001", ["q_00000001"], nim(handler), Tools())
    assert r.status == "ok" and errors("Answer", r.answer) == []
    second = bodies[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "call-7"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call-7"
    assert json.loads(second[-2]["tool_calls"][0]["function"]["arguments"]) == {}
