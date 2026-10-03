"""Provider fallback (llm.fallback, human decision 2026-10-03) and the OpenAI provider, with
fakes and a mock transport: no key, no network. A failed provider hands the whole question to
the next one in llm.chain(); a canary block never does."""
import json

import httpx
import pytest
from fastapi import HTTPException

from agent import agent as agent_mod
from agent import api, llm
from agent.agent import AgentResult
from common.config import cfg

DECL = [{"name": "get_slow_templates", "description": "d", "parameters": {"type": "object", "properties": {}}}]


def test_chain_is_the_provider_then_the_fallbacks(monkeypatch):
    monkeypatch.delenv("BT_LLM_PROVIDER", raising=False)
    names = llm.chain()
    assert names[0] == cfg("llm.provider")
    assert names[1:] == [n for n in cfg("llm.fallback") if n != cfg("llm.provider")]
    assert len(names) == len(set(names))


def test_an_explicit_provider_or_air_gapped_mode_never_fails_over(monkeypatch):
    assert llm.chain("nim") == ["nim"]
    monkeypatch.setenv("BT_LLM_PROVIDER", "ollama")
    assert llm.chain() == ["ollama"]


def test_ollama_cannot_be_a_fallback(monkeypatch):
    monkeypatch.delenv("BT_LLM_PROVIDER", raising=False)
    real = llm.cfg
    monkeypatch.setattr(llm, "cfg", lambda k: ["ollama"] if k == "llm.fallback" else real(k))
    with pytest.raises(ValueError):
        llm.chain()


def test_openai_request_uses_its_own_url_and_token_field(monkeypatch):
    monkeypatch.setattr(llm.gw, "post", lambda p, b: {"payload_id": "pay_00000001", "verdict": "allow", "canary_hits": []})
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})
    out = llm.OpenAIChat("some-model", "k", httpx.MockTransport(handler), sleep=lambda s: None).generate("sys", [], DECL)
    assert out["candidates"][0]["content"]["parts"] == [{"text": "ok"}]
    assert str(seen[0].url) == cfg("llm.openai.base_url").rstrip("/") + "/chat/completions"
    body = json.loads(seen[0].content)
    assert body[cfg("llm.openai.max_tokens_field")] == cfg("llm.openai.max_tokens")
    assert ("temperature" in body) == bool(cfg("llm.openai.send_temperature"))


def test_openai_without_a_key_or_model_refuses_to_start(monkeypatch):
    monkeypatch.delenv(cfg("llm.openai.api_key_env"), raising=False)
    with pytest.raises(llm.MissingKey):
        llm.provider(name="openai", model="m")
    monkeypatch.setenv(cfg("llm.openai.api_key_env"), "k")
    real = llm.cfg
    monkeypatch.setattr(llm, "cfg", lambda k: "" if k == "llm.openai.model" else real(k))
    with pytest.raises(llm.MissingKey):
        llm.provider(name="openai")


class Fake:
    def __init__(self, name):
        self.name, self.model, self.tool_call_errors = name, f"{name}-model", []


@pytest.fixture
def chain(monkeypatch):
    """gemini, then openai, then nim; each provider's behaviour set per test in `fail`."""
    fail: dict[str, Exception] = {}
    asked: list[str] = []
    monkeypatch.setattr(llm, "chain", lambda name=None: [name] if name else ["gemini", "openai", "nim"])

    def provider(transport=None, sleep=None, name=None, model=None):
        if isinstance(fail.get(name), llm.MissingKey):
            raise fail[name]
        return Fake(name)

    def ask(qid, tids, p, toolbox=None, on_event=None):
        asked.append(p.name)
        if p.name in fail:
            raise fail[p.name]
        return AgentResult("ok", {"question_id": qid, "text": "answer", "numbers": []})
    monkeypatch.setattr(llm, "provider", provider)
    monkeypatch.setattr(agent_mod, "ask", ask)
    return fail, asked


def body(**kw):
    return {"question_id": "qn_00000001", "template_ids": [], **kw}


def test_a_failed_provider_hands_the_question_to_the_next(chain):
    fail, asked = chain
    fail["gemini"] = llm.RateLimited("HTTP 429 on all 5 attempts")
    fail["openai"] = llm.MissingKey("OPENAI_API_KEY is not set")
    out = api.ai_ask(body())
    assert out["status"] == "ok" and out["llm"] == {"provider": "nim", "model": "nim-model"}
    assert [f["provider"] for f in out["failovers"]] == ["gemini", "openai"]
    assert asked == ["gemini", "nim"]
    assert any("asking nim instead" in e for e in api.EVENTS["qn_00000001"])


@pytest.mark.parametrize("exc", [httpx.ConnectError("down"), httpx.ReadTimeout("slow"),
                                 llm.MalformedReply("no choices")])
def test_transport_errors_and_bad_replies_fail_over(chain, exc):
    fail, asked = chain
    fail["gemini"] = exc
    assert api.ai_ask(body())["llm"]["provider"] == "openai"


def test_a_canary_block_is_never_failed_over(chain):
    fail, asked = chain
    fail["gemini"] = llm.OutboundBlocked({"payload_id": "pay_00000002"})
    with pytest.raises(HTTPException) as e:
        api.ai_ask(body())
    assert e.value.status_code == 403 and asked == ["gemini"]


def test_when_every_provider_fails_the_last_error_is_reported(chain):
    fail, asked = chain
    for n in ("gemini", "openai", "nim"):
        fail[n] = llm.RateLimited("429")
    with pytest.raises(HTTPException) as e:
        api.ai_ask(body())
    assert e.value.status_code == 503 and asked == ["gemini", "openai", "nim"]


def test_an_explicit_provider_is_not_failed_over(chain):
    fail, asked = chain
    fail["nim"] = llm.RateLimited("429")
    with pytest.raises(HTTPException):
        api.ai_ask(body(llm={"provider": "nim"}))
    assert asked == ["nim"]
