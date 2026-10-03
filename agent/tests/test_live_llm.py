"""Live Gemini tests. Run inside the ai container (the only one with the key and internet):

    docker compose ... exec ai python -m pytest agent/tests/test_live_llm.py

Skipped, with the reason shown, when GEMINI_API_KEY is not set. This is a component test;
e2e/test_q1.py fails instead of skipping when the key is missing (PLAN.md requirement 1).
"""
import os

import httpx
import pytest

from agent import agent as agent_mod
from agent import gateway_client as gw
from agent import llm
from common.config import cfg
from contracts.validate import errors

needs_key = pytest.mark.skipif(not os.environ.get(cfg("llm.api_key_env")),
                               reason=f"{cfg('llm.api_key_env')} is not set; the live LLM path is untested")


@needs_key
def test_configured_model_exists():
    """Confirms config llm.model against the API's own model list (not the docs page)."""
    r = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models/{cfg('llm.model')}",
                  headers={"x-goog-api-key": os.environ[cfg("llm.api_key_env")]}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert "generateContent" in r.json().get("supportedGenerationMethods", [])


@needs_key
def test_live_q1_answer_passes_the_number_checker():
    tid = gw.get("/v1/templates/slow")[0]["template_id"]
    events = []
    r = agent_mod.ask("qn_0000feed", [tid], llm.provider(), on_event=events.append)
    assert r.status == "ok", (r.unmatched, events)
    assert errors("Answer", r.answer) == []
    assert {c["name"] for c in r.tool_calls} >= {"simulate"}
