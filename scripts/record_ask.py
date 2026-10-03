"""make record-ask: record one live Ask session for the public site's /ask page.

Runs one question through the gateway and the ai service (needs make up, make seed and an LLM
key), then writes site/web/src/data/ask_replay.json with what the AI side saw and said: question
id, template codes, hashed answer and its numbers, number-checker status, agent events, the
configuration and the twin measurement the agent made, and ledger totals before and after.

Never written: the question text (the resolver phrases name real tables), any dehashed text,
and the approve files (real names). Refuses to write when a forbidden name or a canary value
appears anywhere in the record (scripts/public_names.py).

    python -m scripts.record_ask ["question"]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from common.config import REPO_ROOT, cfg
from scripts.export_results import git_commit
from scripts.public_names import leaks

OUT = REPO_ROOT / "site" / "web" / "src" / "data" / "ask_replay.json"
DEFAULT_QUESTION = "Why is the weekly sales dashboard timing out?"   # same as the dashboard's Ask page


def build(qid: str, tids: list[str], body: dict, events: list[str], llm: dict, before: dict, after: dict,
          commit: str, now: str) -> dict:
    sim = body.get("simulation")
    return {
        "recorded": True,
        "recorded_at": now,
        "git_commit": commit,
        "model": f"{llm.get('provider', 'unknown')} {llm.get('model', '')}".strip(),
        "question_id": qid,
        "template_ids": tids,
        "status": body["status"],
        "answer": {"text": body["answer"]["text"], "numbers": body["answer"].get("numbers", [])},
        "unmatched": body.get("unmatched", []),
        "events": events,
        "tool_calls": body.get("tool_calls", 0),
        "config": body.get("config"),
        "simulation": None if not sim else {
            "templates": [{k: t[k] for k in ("template_id", "before_ms", "after_ms") if k in t} for t in sim["templates"]],
            "runs": sim.get("runs"), "write_ms_delta": sim.get("write_ms_delta"), "storage_mb_delta": sim.get("storage_mb_delta"),
        },
        "ledger": {"payloads_before": before["outbound_payloads"], "payloads_after": after["outbound_payloads"],
                   "canary_hits_after": after["outbound_canary_hits"]},
    }


def write(doc: dict, out=OUT) -> int:
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    bad = leaks(text)
    if bad or chr(0x2014) in text or chr(0x2013) in text:
        print(f"refused: the record holds {', '.join(bad) or 'an em or en dash'}; nothing written", file=sys.stderr)
        return 1
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def record(question: str) -> dict:
    import httpx   # in the tools image; imported here so the unit tests run without it

    timeout = float(cfg("web.ask_timeout_s"))
    gw, ai = os.environ["GATEWAY_URL"].rstrip("/"), os.environ["AI_URL"].rstrip("/")

    def get(url: str) -> dict:
        r = httpx.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()

    before = get(f"{gw}/v1/ledger")
    res = httpx.post(f"{gw}/v1/ask/resolve", json={"question": question}, timeout=timeout)
    res.raise_for_status()
    qid, tids = res.json()["question_id"], res.json()["template_ids"]
    r = httpx.post(f"{ai}/ai/ask", json={"question_id": qid, "template_ids": tids}, timeout=timeout)
    if r.status_code != 200:
        raise SystemExit(f"/ai/ask failed: HTTP {r.status_code} {r.text[:300]}")
    events = get(f"{ai}/ai/ask/{qid}/events")["events"]
    return build(qid, tids, r.json(), events, get(f"{ai}/ai/llm"), before, get(f"{gw}/v1/ledger"),
                 git_commit(), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def main(argv: list[str]) -> int:
    return write(record(argv[0] if argv else DEFAULT_QUESTION))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
