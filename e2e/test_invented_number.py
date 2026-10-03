"""Scenario (doc, Testing plan: invented-number check): an answer with a number that no tool
returned is blocked by the number checker. No LLM API call.

Run by make e2e-offline, which recreates ai in air-gapped mode (BT_LLM_PROVIDER=ollama, the
production switch) and starts the scripted stand-in e2e/standin_llm.py on llm.ollama.base_url.
/ai/ask then runs the real tool loop through the real gateway; the stand-in answers with one
number copied from get_slow_templates and the planted PLANTED. Asserts: the answer is blocked
after llm.checker_retries retries, PLANTED is the only unmatched number (the copied one passed),
and every LLM request of the run went through the outbound scan with no canary hit.
"""
import time
from datetime import datetime, timezone

import httpx

from common.config import cfg
from e2e.standin_llm import PLANTED
from e2e.test_q1 import AI, gw

TIMEOUT = 300.0


def wait_for_ai(limit_s: float = 60) -> None:
    """ai was just recreated (air-gapped or back online); uvicorn needs a moment to listen."""
    end = time.time() + limit_s
    while True:
        try:
            if httpx.get(AI + "/healthz", timeout=5).status_code == 200:
                return
        except httpx.TransportError:
            if time.time() > end:
                raise
        time.sleep(1)


def test_invented_number_is_blocked():
    wait_for_ai()
    started, run_started = time.time(), datetime.now(timezone.utc)
    info = httpx.get(AI + "/ai/llm", timeout=30).json()
    assert info["provider"] == "ollama", "ai is not in air-gapped mode against the stand-in: run make e2e-offline"

    resolved = gw("/v1/ask/resolve", {"question": "Why is the weekly sales dashboard timing out?"})
    assert resolved["template_ids"], "no template resolved: run make seed"
    r = httpx.post(AI + "/ai/ask", json={"question_id": resolved["question_id"], "template_ids": resolved["template_ids"]},
                   timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    print("events:", *body["events"], sep="\n  ")
    assert body["status"] == "blocked_by_checker", body
    assert body["answer"] is None
    assert body["unmatched"] == [PLANTED]
    rejected = [e for e in body["events"] if e.startswith("number checker rejected")]
    assert len(rejected) == 1 + int(cfg("llm.checker_retries"))
    assert [c["name"] for c in body["tool_calls"]] == ["get_slow_templates"]

    sent = [e for e in gw("/v1/ledger")["entries"] if e["destination"] == "llm"
            and datetime.fromisoformat(e["time"].replace("Z", "+00:00")) >= run_started]
    assert len(sent) == 2 + int(cfg("llm.checker_retries"))    # tool call, answer, each retry
    assert all(e["verdict"] == "allow" and not e["canary_hits"] for e in sent)

    elapsed = time.time() - started
    print(f"invented-number scenario: {elapsed:.1f} s")
    assert elapsed < cfg("tests.fast_suite_limit_s"), f"took {elapsed:.0f} s"
