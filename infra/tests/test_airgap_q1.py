"""Acceptance (doc, Whole system): air-gapped mode answers Q1 with networking to the LLM API
switched off. Runs in the tools container after make airgap (make test-airgap), the way the
dashboard asks: the gateway resolves the DBA's question privately, then ai answers through
the local model.

Skips only when ai cannot connect to Ollama. Fails on everything else: ai not in air-gapped
mode, ai still reaching the LLM API host, the model missing, an overflow, a malformed reply,
or an answer the number checker blocked.
"""
from datetime import datetime, timezone

import httpx
import pytest

from agent import llm
from common.config import cfg
from e2e.test_q1 import AI, dehash, gw

TIMEOUT_S = 900.0     # a small local model may take several seconds per turn, plus the tools


def test_airgap_answers_q1():
    started = datetime.now(timezone.utc)
    info = httpx.get(AI + "/ai/llm", timeout=30).json()
    assert info["provider"] == "ollama", "ai is not in air-gapped mode: run make airgap"
    assert info["label"] == llm.LABEL_OLLAMA.format(model=cfg("llm.ollama.model"), route=llm.ROUTE_NONE), info

    slow = gw("/v1/templates/slow")
    q1 = next((t for t in slow if dehash(t["template_id"]).startswith('query "SELECT SUM(amount) FROM sales WHERE region_id')), None)
    assert q1 is not None, "Q1 is not among the slow templates: run make seed"
    resolved = gw("/v1/ask/resolve", {"question": "Why is the weekly sales dashboard timing out?"})
    assert q1["template_id"] in resolved["template_ids"]

    r = httpx.post(AI + "/ai/ask", json={"question_id": resolved["question_id"], "template_ids": resolved["template_ids"]},
                   timeout=TIMEOUT_S)
    detail = r.json().get("detail") if r.status_code == 503 else None
    if isinstance(detail, dict) and detail.get("error") in ("ConnectError", "ConnectTimeout"):
        pytest.skip(f"ai cannot reach Ollama at {cfg('llm.ollama.base_url')}: {detail['detail']}; see README.md, air-gapped mode")
    assert r.status_code == 200, r.text
    body = r.json()
    print("events:", *body["events"], sep="\n  ")
    assert body["status"] == "ok", f"number checker blocked the answer: {body['unmatched']}"
    calls = {c["tool_call_id"] for c in body["tool_calls"]}
    assert body["answer"]["numbers"], "the answer cites no numbers"
    assert all(n["tool_call_id"] in calls for n in body["answer"]["numbers"])
    print("answer:", dehash(body["answer"]["text"]))

    sent = [e for e in gw("/v1/ledger")["entries"] if e["destination"] == "llm"
            and datetime.fromisoformat(e["time"].replace("Z", "+00:00")) >= started]
    assert sent and all(e["verdict"] == "allow" and not e["canary_hits"] for e in sent)
