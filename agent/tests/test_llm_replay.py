"""Replay recorded live runs (agent/tests/fixtures/llm/<provider>__<model>.json, written by
make llm-bench) through the real provider adapter, tool loop and number checker, with no
network. Each fixture must reproduce its recorded outcome, and every request body must again
go through the outbound scan."""
import json
from pathlib import Path

import pytest

from agent import agent as agent_mod
from agent import llm
from agent.recording import ReplayToolbox, ReplayTransport

FIXTURES = Path(__file__).parent / "fixtures" / "llm"
FILES = sorted(FIXTURES.glob("*.json")) if FIXTURES.exists() else []


@pytest.mark.parametrize("provider", ["gemini", "nim"])
def test_each_provider_has_a_recorded_run(provider):
    if not any(f.name.startswith(provider + "__") for f in FILES):
        pytest.skip(f"no recorded {provider} run yet: run make llm-bench with that provider's key in .env")


@pytest.mark.parametrize("path", FILES, ids=[f.stem for f in FILES])
def test_recorded_run_replays_to_the_same_outcome(path, monkeypatch):
    fx = json.loads(path.read_text(encoding="utf-8"))
    scanned = []

    def post(p, body):
        assert p == "/v1/ledger/outbound"
        scanned.append(body["body"])
        return {"payload_id": "pay_00000001", "verdict": "allow", "canary_hits": []}
    monkeypatch.setattr(llm.gw, "post", post)
    monkeypatch.setenv("GEMINI_API_KEY", "replay")
    monkeypatch.setenv("NVIDIA_API_KEY", "replay")
    transport = ReplayTransport(fx["exchanges"])
    provider = llm.provider(transport, sleep=lambda s: None, name=fx["provider"], model=fx["model"])
    if hasattr(provider, "_clock"):
        provider._clock = lambda: 0.0                    # no spacing waits in a replay
    r = agent_mod.ask(fx["question_id"], fx["template_ids"], provider, ReplayToolbox(fx["tool_calls"]))
    assert r.status == fx["outcome"]["status"]
    assert r.answer == fx["outcome"]["answer"]
    assert not transport.exchanges, "the replay used fewer LLM calls than were recorded"
    assert len(scanned) == len(fx["exchanges"])
