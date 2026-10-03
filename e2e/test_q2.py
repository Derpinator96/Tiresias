"""End-to-end test for Q2, the monthly category report (run in the tools container after
make up and make seed):

    docker compose -f infra/docker-compose.yml --project-directory . run --rm -T tools \
        python -m pytest -p no:cacheprovider -v -s e2e/test_q2.py

One test drives the whole flow through the real services, the way the dashboard does:
1. Q2 is slow before the fix;
2. the search's configuration holds Q2's date_trunc rewrite plus at least one index, chosen as
   the best twin measurement of the top configurations (which index it is gets printed: on the
   step 23 stack it is the (region_id, transaction_date) index that serves Q1 and the
   two-region query, not a Q2 index; see rl/NOTES.md);
3. Q2 is over tests.q2_min_twin_speedup faster on the twin with that configuration, measured
   fresh at the gateway;
4. the rewrite carries its honest status, TestedOnly (VeriEQL cannot encode date_trunc; the twin
   checksum matches), and the LLM's answer reports it after calling verify;
5. zero canary hits across every payload this run sent to the AI side or the LLM;
6. every number in the LLM's answer traces to a tool result.

It fails, never skips, when GEMINI_API_KEY is missing. No time limit is asserted: the search
re-checks its top configurations on the twin, which takes minutes on a loaded machine; the
elapsed time is printed. It writes no run record (scripts/export_results.py reads Q1's).
"""
import os
import re
import time
from datetime import datetime, timezone

import httpx

from common.config import cfg
from db import canaries

GW = os.environ.get("GATEWAY_URL", "http://gateway:8000")
AI = os.environ.get("AI_URL", "http://ai:8100")
TIMEOUT = 900.0
RULE = "date_trunc_eq_to_range"


def gw(path, body=None):
    r = httpx.request("POST" if body is not None else "GET", GW + path, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def dehash(text: str) -> str:
    return gw("/v1/answers/dehash", {"question_id": "qn_00000000", "text": text, "numbers": []})["text"]


def test_q2_end_to_end():
    started = time.time()
    run_started = datetime.now(timezone.utc)
    assert os.environ.get("GEMINI_API_KEY_PRESENT") == "yes", \
        "GEMINI_API_KEY is not set in .env: the LLM step cannot run, so the end-to-end test fails"

    # 1. Q2 is slow before the fix.
    slow = gw("/v1/templates/slow")
    q2 = next((t for t in slow if dehash(t["template_id"]).startswith('query "SELECT p.category, SUM(s.amount) FROM sales s')), None)
    assert q2 is not None, "Q2 is not among the slow templates"
    assert q2["mean_ms"] > cfg("workload.slow_query_ms")

    question = f"Why is the monthly category sales report so slow? {canaries.QUESTION.value}"
    resolved = gw("/v1/ask/resolve", {"question": question})
    assert q2["template_id"] in resolved["template_ids"]

    # 2. Rewrite plus index, chosen by the twin re-check.
    r = httpx.post(AI + "/ai/rl/run", json={}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    rl = r.json()
    actions = rl["config"]["actions"]
    rewrite = {"type": "rewrite", "template_id": q2["template_id"], "rule_id": RULE}
    assert any({k: a.get(k) for k in rewrite} == rewrite for a in actions), actions
    indexes = [a for a in actions if a["type"] == "add_index"]
    assert indexes, "the search chose no index"
    assert rl["final_choice"] == "best measured on the twin"
    assert sum(e["chosen"] for e in rl["top_configs"]) == 1

    # 3. Over the threshold on the twin, measured fresh.
    sim = gw("/v1/simulate/twin", rl["config"])
    t = next(x for x in sim["templates"] if x["template_id"] == q2["template_id"])
    speedup = 1 - t["after_ms"] / t["before_ms"]
    print(f"\nQ2 twin {t['before_ms']} ms -> {t['after_ms']} ms, {100 * speedup:.1f}% faster; "
          f"chosen: {[dehash(' '.join([a['table']] + a['columns'])) if a['type'] == 'add_index' else a['rule_id'] for a in actions]}")
    assert speedup > cfg("tests.q2_min_twin_speedup"), (t, speedup)
    checksum = gw("/v1/twin/checksum", {"template_id": q2["template_id"], "config": rl["config"]})
    assert checksum["match"]

    # 4. The rewrite's honest status.
    rw = gw("/v1/rewrite/verify", {"template_id": q2["template_id"], "rule_id": RULE})
    assert rw["status"] == "TestedOnly" and rw["checks"] == {"verieql": "unsupported", "checksum": "match"}
    assert {"template_id": q2["template_id"], "rule_id": RULE, "status": "TestedOnly", "checks": rw["checks"]} in rl["rewrites"]

    # 6. The LLM answers; every number traces to a tool result; it reports the status.
    ask = httpx.post(AI + "/ai/ask", json={"question_id": resolved["question_id"], "template_ids": resolved["template_ids"]},
                     timeout=TIMEOUT)
    assert ask.status_code == 200, ask.text
    body = ask.json()
    assert body["status"] == "ok", f"number checker blocked the answer: {body['unmatched']}"
    answer = body["answer"]
    print("answer:", dehash(answer["text"]))
    call_ids = {c["tool_call_id"] for c in body["tool_calls"]}
    assert answer["numbers"], "the answer cites no numbers"
    assert all(n["tool_call_id"] in call_ids for n in answer["numbers"])
    assert canaries.QUESTION.value not in answer["text"]
    assert "verify" in {c["name"] for c in body["tool_calls"]}, body["tool_calls"]
    assert re.search(r"tested ?only", answer["text"], re.IGNORECASE), answer["text"]

    # 5. Zero canary hits in every payload of this run.
    ledger = gw("/v1/ledger")["entries"]
    this_run = [e for e in ledger if e["destination"] in ("ai", "llm")
                and datetime.fromisoformat(e["time"].replace("Z", "+00:00")) >= run_started]
    assert this_run, "no payloads were ledgered"
    assert sum(len(e["canary_hits"]) for e in this_run) == 0
    assert any(e["destination"] == "llm" for e in this_run), "no LLM request went through the outbound scan"
    print(f"elapsed {time.time() - started:.0f} s, {len(this_run)} payloads, 0 canary hits, "
          f"{len(answer['numbers'])} numbers checked, {len(body['tool_calls'])} tool calls")
