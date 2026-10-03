"""End-to-end test for Q1, the hero query (run in the tools container after make up and make seed):

    make e2e

One test drives the whole flow through the real services, the way the dashboard does, and
asserts the five outcomes from the session brief:
1. Q1 is slow before the fix;
2. the recommended index is the (region_id, transaction_date) codes, in that order;
3. Q1 is over 50% faster on the twin after the fix;
4. zero canary hits across every payload this run sent to the AI side or the LLM;
5. every number in the LLM's answer traces to a tool result.

It fails, never skips, when GEMINI_API_KEY is missing (PLAN.md requirement 1).
A passing run writes runs/latest.json, which scripts/export_results.py turns into results.json.
"""
import json
import os
import secrets
import time
from datetime import datetime, timezone

import httpx

from common.config import REPO_ROOT, cfg
from db import canaries

GW = os.environ.get("GATEWAY_URL", "http://gateway:8000")
AI = os.environ.get("AI_URL", "http://ai:8100")
TIMEOUT = 300.0


def gw(path, body=None):
    r = httpx.request("POST" if body is not None else "GET", GW + path, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def dehash(text: str) -> str:
    return gw("/v1/answers/dehash", {"question_id": "qn_00000000", "text": text, "numbers": []})["text"]


def test_q1_end_to_end():
    started = time.time()
    run_started = datetime.now(timezone.utc)
    assert os.environ.get("GEMINI_API_KEY_PRESENT") == "yes", \
        "GEMINI_API_KEY is not set in .env: the LLM step cannot run, so the end-to-end test fails"

    # 1. Q1 is slow before the fix (pg_stat_statements mean, through the gateway).
    slow = gw("/v1/templates/slow")
    q1 = next((t for t in slow if dehash(t["template_id"]).startswith('query "SELECT SUM(amount) FROM sales WHERE region_id')), None)
    assert q1 is not None, "Q1 is not among the slow templates"
    assert q1["mean_ms"] > cfg("workload.slow_query_ms")

    # The DBA's question, with a canary in it. The gateway resolves it locally.
    question = f"Why is the weekly sales dashboard timing out? {canaries.QUESTION.value}"
    resolved = gw("/v1/ask/resolve", {"question": question})
    assert q1["template_id"] in resolved["template_ids"]

    # 2. The recommended index is (region_id, transaction_date), in that order.
    rl = httpx.post(AI + "/ai/rl/run", json={}, timeout=TIMEOUT).json()
    actions = rl["config"]["actions"]
    assert actions, "the search recommended nothing"
    first = actions[0]
    assert dehash(" ".join([first["table"]] + first["columns"])) == "sales region_id transaction_date"

    # 3. Over 50% faster on the twin, measured.
    sim = gw("/v1/simulate/twin", rl["config"])
    t = next(x for x in sim["templates"] if x["template_id"] == q1["template_id"])
    speedup = 1 - t["after_ms"] / t["before_ms"]
    assert speedup > cfg("tests.q1_min_twin_speedup"), (t, speedup)
    checksum = gw("/v1/twin/checksum", {"template_id": q1["template_id"], "config": rl["config"]})
    assert checksum["match"]

    # 5. The LLM answers, and every number in its answer traces to a tool result.
    ask = httpx.post(AI + "/ai/ask", json={"question_id": resolved["question_id"], "template_ids": resolved["template_ids"]},
                     timeout=TIMEOUT)
    assert ask.status_code == 200, ask.text
    body = ask.json()
    assert body["status"] == "ok", f"number checker blocked the answer: {body['unmatched']}"
    answer = body["answer"]
    call_ids = {c["tool_call_id"] for c in body["tool_calls"]}
    assert answer["numbers"], "the answer cites no numbers"
    assert all(n["tool_call_id"] in call_ids for n in answer["numbers"])
    assert canaries.QUESTION.value not in answer["text"]

    # 4. Zero canary hits in every payload of this run (AI-facing responses and LLM bodies).
    ledger = gw("/v1/ledger")["entries"]
    this_run = [e for e in ledger if e["destination"] in ("ai", "llm")
                and datetime.fromisoformat(e["time"].replace("Z", "+00:00")) >= run_started]
    assert this_run, "no payloads were ledgered"
    assert sum(len(e["canary_hits"]) for e in this_run) == 0
    assert any(e["destination"] == "llm" for e in this_run), "no LLM request went through the outbound scan"

    elapsed = time.time() - started
    assert elapsed < cfg("tests.fast_suite_limit_s"), f"e2e took {elapsed:.0f} s"

    # Run record for scripts/export_results.py. Hashed codes and measured numbers only.
    tables = gw("/v1/meta/tables")
    sales = next(x for x in tables if x["table"] == first["table"])
    record = {
        "run_id": "run_" + secrets.token_hex(4),
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_s": round(elapsed, 1),
        "dataset": {"hero_table_rows": sales["rows"], "hero_table_size_mb": sales["size_mb"]},
        "q1": {"mean_ms_before": q1["mean_ms"], "slow_threshold_ms": cfg("workload.slow_query_ms")},
        "twin": {"before_ms": t["before_ms"], "after_ms": t["after_ms"], "speedup_pct": round(100 * speedup, 1),
                 "storage_mb": sim["storage_mb_delta"], "runs": sim["runs"], "checksum_match": checksum["match"]},
        "search": {"label": rl["label"], "predicted_before_ms": rl["baseline_predicted_ms"], "predicted_after_ms": rl["final_predicted_ms"],
                   "estimator_label": rl["estimator_label"], "recommended_columns": len(first["columns"])},
        "privacy": {"payloads": len(this_run), "llm_payloads": sum(e["destination"] == "llm" for e in this_run),
                    "canary_hits": 0, "canaries_planted": cfg("canaries.planted_target")},
        "llm": {"provider": cfg("llm.provider"), "model": cfg("llm.model"), "tool_calls": len(body["tool_calls"]),
                "numbers_checked": len(answer["numbers"])},
    }
    os.makedirs(REPO_ROOT / "runs", exist_ok=True)
    (REPO_ROOT / "runs" / "latest.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
