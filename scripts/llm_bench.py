"""make llm-bench: choose a NIM model by running the Q1 flow on each candidate, and record
fixtures for the replay tests. Runs in the tools container; every LLM call goes through the ai
service (and so through the outbound scan and the egress allowlist proxy).

    python -m scripts.llm_bench models                    # list NIM models and the candidates
    python -m scripts.llm_bench probe                     # one synthetic tool-call request per candidate
    python -m scripts.llm_bench run --provider nim        # probe, then Q1 on the first passing candidates
    python -m scripts.llm_bench run --provider nim --models a,b
    python -m scripts.llm_bench run --provider gemini     # the configured Gemini model
    python -m scripts.llm_bench run --provider openai --models <id>   # an OpenAI model (no listing step)
    python -m scripts.llm_bench ratetest --models m --n 45  # back-to-back synthetic requests: how often 429?

Per model it reports tool-call errors, the number checker's result, LLM seconds (time spent in
LLM requests only) and total seconds per answer (which also include the index search and twin
measurement the tools run; those are cached after the first run, so compare LLM seconds).
Results go to runs/llm_bench_<provider>.json. A passing run is also written, after a canary
scan, to agent/tests/fixtures/llm/<provider>__<model>.json for the replay tests.
Live models are run strictly one after another: the free NIM tier allows about 40 requests
per minute per model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import httpx

from common.config import REPO_ROOT, cfg
from gateway.canary_scan import Scanner

GW = os.environ.get("GATEWAY_URL", "http://gateway:8000")
AI = os.environ.get("AI_URL", "http://ai:8100")
QUESTION = "Why is the weekly sales dashboard timing out?"
FIXTURES = REPO_ROOT / "agent" / "tests" / "fixtures" / "llm"
TIMEOUT = 1800.0


def candidates(models: list[str], limit: int | None = None) -> list[str]:
    """Models worth a tool-calling run: not excluded; preferred families first, then instruct
    models; at most `limit` (default llm.nim.bench_candidates)."""
    excluded = [p.lower() for p in cfg("llm.nim.exclude_patterns")]
    prefer = [p.lower() for p in cfg("llm.nim.prefer_families")]
    keep = [m for m in models if not any(x in m.lower() for x in excluded)]
    if limit != 0:      # the short list: preferred family or instruct models only
        keep = [m for m in keep if any(f in m.lower() for f in prefer) or "instruct" in m.lower()]

    def rank(m: str) -> tuple:
        low = m.lower()
        return (not any(f in low for f in prefer), "instruct" not in low, m)
    ranked = sorted(keep, key=rank)
    return ranked if limit == 0 else ranked[: int(cfg("llm.nim.bench_candidates")) if limit is None else limit]


def probe(models: list[str]) -> list[dict]:
    """One synthetic tool-call request per model, one after another (no data in it)."""
    out = []
    for m in models:
        r = httpx.post(AI + "/ai/llm/probe", json={"provider": "nim", "model": m}, timeout=300)
        row = r.json() if r.status_code == 200 else {"model": m, "tool_call": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        print(json.dumps(row), flush=True)
        out.append(row)
    return out


def ratetest(provider: str, model: str, n: int) -> dict:
    """n synthetic tool-call requests to one model, back to back with no client-side spacing (each
    probe uses a new provider object), one after another. Counts every 429 and 5xx the API sent,
    including the ones the adapter retried through, and how long each request took."""
    import statistics
    import time
    started, rows = time.monotonic(), []
    for _ in range(n):
        r = httpx.post(AI + "/ai/llm/probe", json={"provider": provider, "model": model}, timeout=600)
        rows.append(r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}", "events": [], "seconds": 0})
    elapsed = time.monotonic() - started
    retries = [e for r in rows for e in r.get("events", []) if "retrying" in e]
    secs = sorted(r["seconds"] for r in rows)
    return {"provider": provider, "model": model, "requests": n, "elapsed_s": round(elapsed, 1),
            "requests_per_minute": round(60 * n / elapsed, 1),
            "status_429": sum(e.startswith("rate limited") for e in retries),
            "status_5xx": sum(e.startswith("LLM service unavailable") for e in retries),
            "connection_failures": sum(e.startswith("LLM host unreachable") for e in retries),
            "failed_after_retries": sum("error" in r for r in rows),
            "tool_call_ok": sum(bool(r.get("tool_call")) for r in rows),
            "seconds_p50": round(statistics.median(secs), 2), "seconds_max": round(secs[-1], 2),
            "errors": sorted({r["error"][:120] for r in rows if "error" in r})}


def tool_calling_candidates() -> tuple[list[str], list[dict]]:
    """Probe every non-excluded model in rank order (preferred family first, then instruct
    models, then the rest); keep the first llm.nim.bench_candidates that return a tool call.
    Widened from family and instruct models only on 2026-10-03: most listed models return 404
    for this account, and only one of those returned a tool call."""
    want = int(cfg("llm.nim.bench_candidates"))
    rows, keep = [], []
    for m in candidates(list_models(), limit=0):
        row = probe([m])[0]
        rows.append(row)
        if row.get("tool_call"):
            keep.append(m)
            if len(keep) == want:
                break
    return keep, rows


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def list_models() -> list[str]:
    r = httpx.get(AI + "/ai/llm/models", params={"provider": "nim"}, timeout=60)
    r.raise_for_status()
    return r.json()["models"]


def run_one(provider: str, model: str | None) -> dict:
    res = httpx.post(GW + "/v1/ask/resolve", json={"question": QUESTION}, timeout=60).json()
    body = {"question_id": res["question_id"], "template_ids": res["template_ids"],
            "llm": {"provider": provider, **({"model": model} if model else {})}, "record": True}
    r = httpx.post(AI + "/ai/ask", json=body, timeout=TIMEOUT)
    try:
        out = r.json()
    except ValueError:
        out = {"detail": r.text[:300]}
    if r.status_code != 200:
        detail = out.get("detail")
        return {"model": model, "http": r.status_code, "ok": False,
                "error": detail.get("detail") or detail.get("error") if isinstance(detail, dict) else detail}
    rec = out["record"]
    tool_errors = list(out["tool_call_errors"]) + [
        f"{t['name']}: {t['result']['error']}" for t in rec["tool_calls"]
        if isinstance(t["result"], dict) and "error" in t["result"]]
    return {"model": out["llm"]["model"], "http": 200, "ok": out["status"] == "ok",
            "checker": "pass" if out["status"] == "ok" else f"blocked ({', '.join(out['unmatched'])})",
            "tool_calls": len(out["tool_calls"]), "tool_call_errors": tool_errors,
            "llm_requests": len(rec["exchanges"]),
            "llm_seconds": round(sum(e.get("seconds", 0) for e in rec["exchanges"]), 2),
            "seconds": out["seconds"], "answer": (out["answer"] or {}).get("text"),
            "_fixture": {"provider": provider, "model": out["llm"]["model"], "question_id": res["question_id"],
                         "template_ids": res["template_ids"], "recorded_at": datetime.now(timezone.utc).isoformat(),
                         "outcome": {"status": out["status"], "answer": out["answer"], "unmatched": out["unmatched"]},
                         **rec}}


def write_fixture(fx: dict) -> str:
    text = json.dumps(fx, indent=1)
    hits = Scanner().scan(text)
    if hits:
        raise RuntimeError(f"fixture holds canary fragments {hits}; not written")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{fx['provider']}__{slug(fx['model'])}.json"
    path.write_text(text + "\n", encoding="utf-8")
    return str(path.relative_to(REPO_ROOT))


def table(rows: list[dict]) -> str:
    lines = ["| model | number checker | tool-call errors | LLM s | total s | tool calls |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if r["http"] != 200:
            lines.append(f"| {r['model']} | not answered (HTTP {r['http']}: {r['error']}) | - | - | - | - |")
        else:
            lines.append(f"| {r['model']} | {r['checker']} | {len(r['tool_call_errors'])} | {r['llm_seconds']} | "
                         f"{r['seconds']} | {r['tool_calls']} |")
    return "\n".join(lines)


def best(rows: list[dict]) -> dict | None:
    ok = [r for r in rows if r["http"] == 200 and r["ok"]]
    return min(ok, key=lambda r: (len(r["tool_call_errors"]), r["llm_seconds"])) if ok else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["models", "probe", "run", "ratetest"])
    ap.add_argument("--n", type=int, default=45)
    ap.add_argument("--provider", default="nim", choices=["nim", "gemini", "openai"])
    ap.add_argument("--models", default="")
    a = ap.parse_args(argv)
    if a.cmd == "models":
        models = list_models()
        print(f"{len(models)} NIM models listed; candidates: {candidates(models)}")
        print("\n".join(models))
        return 0
    if a.cmd == "ratetest":
        res = [ratetest(a.provider, m, a.n) for m in a.models.split(",") if m]
        (REPO_ROOT / "runs").mkdir(exist_ok=True)
        (REPO_ROOT / "runs" / f"llm_ratetest_{a.provider}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        for r in res:
            print(json.dumps(r))
        return 0
    if a.cmd == "probe":
        keep, rows = tool_calling_candidates()
        (REPO_ROOT / "runs").mkdir(exist_ok=True)
        (REPO_ROOT / "runs" / "llm_probe_nim.json").write_text(json.dumps({"probes": rows, "candidates": keep}, indent=1),
                                                               encoding="utf-8")
        print(f"tool-calling candidates: {keep}")
        return 0 if keep else 1
    probes = []
    models = [m for m in a.models.split(",") if m]
    if not models and a.provider == "nim":
        models, probes = tool_calling_candidates()
    models = models or [None]
    rows = []
    for m in models:                        # strictly sequential: per-model request quotas
        print(f"running Q1 on {a.provider} {m or cfg('llm.model')} ...", flush=True)
        row = run_one(a.provider, m)
        fx = row.pop("_fixture", None)
        if fx and row["ok"]:
            row["fixture"] = write_fixture(fx)
        elif fx:        # blocked: keep the model's last reply (hashed codes only) to see why
            last = fx["exchanges"][-1]["response"] if fx["exchanges"] else None
            row["last_reply"] = last
            row["tool_results"] = {t["tool_call_id"]: t["result"] for t in fx["tool_calls"]}
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "answer"}), flush=True)
    out = {"provider": a.provider, "ran_at": datetime.now(timezone.utc).isoformat(), "probes": probes, "rows": rows,
           "best": (best(rows) or {}).get("model")}
    (REPO_ROOT / "runs").mkdir(exist_ok=True)
    (REPO_ROOT / "runs" / f"llm_bench_{a.provider}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(table(rows))
    print(f"best: {out['best'] or 'none passed'}")
    return 0 if out["best"] else 1


if __name__ == "__main__":
    sys.exit(main())
