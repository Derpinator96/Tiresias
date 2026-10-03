"""Blind Tuner post-deploy check (doc, Detailed component specs, "Approve and deploy").

POST /v1/approve copies this file into the DBA's download with PARAMS filled in: the affected
templates' logged queries (real names, real values), the replay minutes and the threshold. Keep
it with the DBA: it never goes to the AI side.

Run it from the folder that holds migration.sql and rollback.sql:
  1. python post_deploy_check.py baseline   before migration.sql: replays the queries and saves
                                            each template's median latency next to this file
  2. psql -v ON_ERROR_STOP=1 -f migration.sql
  3. python post_deploy_check.py check      replays again; if any template's median is more than
                                            PARAMS["worse_by"] worse, runs rollback.sql
Connection: BT_DSN (a libpq connection string) or the standard PGHOST, PGPORT, PGUSER,
PGPASSWORD and PGDATABASE variables. --minutes overrides the replay length (the demo on the
twin uses a short one). Needs Python 3 and psycopg 3. Prints a JSON report.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import psycopg

PARAMS = {"config_id": None, "minutes": 0, "worse_by": 0, "warmup_runs": 0, "queries": {}}  # filled by POST /v1/approve
HERE = Path(__file__).resolve().parent


def statements(text: str) -> list[str]:
    """The statements of a generated .sql file: blank and `--` lines skipped, a statement ends
    on a line ending in `;`. ponytail: fits the files approve writes, not arbitrary SQL."""
    out, cur = [], []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("--"):
            continue
        cur.append(line)
        if line.rstrip().endswith(";"):
            out.append("\n".join(cur))
            cur = []
    return out


def run_sql(conn: psycopg.Connection, text: str) -> None:
    """One statement at a time on an autocommit connection: CONCURRENTLY cannot run inside a
    transaction block, and several statements in one call would form one."""
    for s in statements(text):
        conn.execute(s)


def replay(conn: psycopg.Connection, queries: dict[str, str], seconds: float, warmup_runs: int = 0) -> dict[str, dict]:
    """Run every query `warmup_runs` times untimed, then in turn until `seconds` have passed,
    each at least once. Returns template_id -> {median_ms, runs}."""
    for q in list(queries.values()) * warmup_runs:
        conn.execute(q).fetchall()
    times: dict[str, list[float]] = {tid: [] for tid in queries}
    deadline = time.monotonic() + seconds
    while queries:
        for tid, q in queries.items():
            t0 = time.perf_counter()
            conn.execute(q).fetchall()
            times[tid].append((time.perf_counter() - t0) * 1000)
        if time.monotonic() >= deadline:
            break
    return {tid: {"median_ms": statistics.median(t), "runs": len(t)} for tid, t in times.items()}


def worse(before: dict[str, float], after: dict[str, float], worse_by: float) -> dict[str, float]:
    """template_id -> fractional slowdown, for templates whose median grew by more than worse_by."""
    return {tid: after[tid] / before[tid] - 1 for tid in before if after[tid] > before[tid] * (1 + worse_by)}


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description="Replay the affected templates before and after migration.sql.")
    p.add_argument("phase", choices=["baseline", "check"])
    p.add_argument("--minutes", type=float, default=PARAMS["minutes"], help="replay length per phase")
    args = p.parse_args(argv)
    state = HERE / "post_deploy_baseline.json"
    with psycopg.connect(os.environ.get("BT_DSN", ""), autocommit=True) as conn:
        measured = replay(conn, PARAMS["queries"], args.minutes * 60, PARAMS["warmup_runs"])
        report = {"config_id": PARAMS["config_id"], "phase": args.phase, "minutes": args.minutes,
                  "worse_by": PARAMS["worse_by"], "templates": measured}
        if args.phase == "baseline":
            state.write_text(json.dumps(measured), encoding="utf-8")
        else:
            baseline = json.loads(state.read_text(encoding="utf-8"))
            hit = worse({t: v["median_ms"] for t, v in baseline.items()},
                        {t: v["median_ms"] for t, v in measured.items()}, PARAMS["worse_by"])
            if hit:
                run_sql(conn, (HERE / "rollback.sql").read_text(encoding="utf-8"))
            report.update(baseline=baseline, worse=hit, rolled_back=bool(hit))
    print(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    main()
