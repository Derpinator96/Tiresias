"""Twin fidelity (doc, Component 6 step 5 and Detailed component specs, Twin: "twin speedup /
production speedup, reported per query"). Private side; runs in the tools container:

    python -m db.sandbox.fidelity      # make fidelity

For each query in sandbox.fidelity_queries, its configuration (indexes, optional rewrite) is
measured on the twin (twin_measure.measure) and on pg-prod the same way (twin_measure.
before_after): before = the original query without the indexes, after = the rewritten query
(or the same one) with them, each the median of sandbox.timing_runs warm runs.

pg-prod: the indexes exist only while they are measured and are always dropped (try/finally
in before_after; human-approved 2026-10-03). The session is the admin role, which the gateway
never ingests (it reads only workload.app_role), with auto_explain and pg_stat_statements
tracking off for the session, so these runs never become templates or logged plans.

speedup = before ms / after ms. fidelity = twin speedup / production speedup: 1.0 means the
twin predicted production's speedup exactly, below 1.0 that it understated it.

Output: sandbox.fidelity_path, JSON written by main():
    {"generated_at", "label", "twin_label", "runs", "warmup_runs", "speedup", "fidelity",
     "queries": [{"query", "rewrite", "indexes", "twin": {"before_ms", "after_ms", "speedup"},
                  "production": {...same...}, "fidelity", "plan_agrees": {"before", "after"}}]}
"indexes" is the number of indexes; their columns are in config.yaml. The file holds no table
or column name, so the gateway can serve it to the dashboard.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg

from common.config import cfg
from db import workload
from db.sandbox import twin_measure
from db.twin.build import LABEL as TWIN_LABEL
from gateway import rewrite_rules

LABEL = "fidelity: configurations from config.yaml (the doc's expected picks), not from a live search run"
QUERIES = {"q1": workload.q1_sql, "q2": workload.q2_sql, "qor": workload.qor_sql}


def measure_prod(prod_dsn: str, indexes, queries: dict[str, str], after_queries: dict[str, str]):
    """before_after() on pg-prod in a session the gateway never sees. Returns (before, after,
    before operator sequences, after operator sequences)."""
    with psycopg.connect(prod_dsn, autocommit=True) as conn:
        if conn.info.user == cfg("workload.app_role"):
            raise RuntimeError("fidelity must not run as the application role: the gateway ingests its queries")
        conn.execute("SET auto_explain.log_min_duration = -1")
        conn.execute("SET pg_stat_statements.track = 'none'")
        before_ops = {tid: twin_measure.op_sequence(twin_measure._explain(conn, q)) for tid, q in queries.items()}
        before, after, _, after_ops, _ = twin_measure.before_after(conn, indexes, queries, after_queries, "bt_fidelity_")
    return before, after, before_ops, after_ops


def entry(qid: str, rewrite: str | None, n_indexes: int, twin: tuple[float, float], prod: tuple[float, float],
          agrees_before: bool, agrees_after: bool) -> dict:
    """One query's result from (before ms, after ms) on the twin and on pg-prod."""
    ts, ps = twin[0] / twin[1], prod[0] / prod[1]
    side = lambda b, a, s: {"before_ms": round(b, 3), "after_ms": round(a, 3), "speedup": round(s, 3)}
    return {"query": qid, "rewrite": rewrite, "indexes": n_indexes, "twin": side(*twin, ts),
            "production": side(*prod, ps), "fidelity": round(ts / ps, 3),
            "plan_agrees": {"before": agrees_before, "after": agrees_after}}


def measure_query(prod_dsn: str, twin_dsn: str, qid: str, case: dict) -> dict:
    q = QUERIES[qid]()
    after = rewrite_rules.rewrite(q, case["rewrite"]) if case["rewrite"] else q
    indexes = [(t, list(cols)) for t, cols in case["indexes"]]
    tw = twin_measure.measure(prod_dsn, twin_dsn, indexes, {qid: q}, {qid: after})
    before, after_ms, _, after_ops = measure_prod(prod_dsn, indexes, {qid: q}, {qid: after})
    return entry(qid, case["rewrite"], len(indexes), (tw.before_ms[qid], tw.after_ms[qid]), (before[qid], after_ms[qid]),
                 tw.plan_agreement[qid], tw.after_ops[qid] == after_ops[qid])


def run(prod_dsn: str, twin_dsn: str) -> dict:
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": LABEL,
            "twin_label": TWIN_LABEL, "runs": int(cfg("sandbox.timing_runs")), "warmup_runs": int(cfg("sandbox.warmup_runs")),
            "speedup": "before_ms / after_ms", "fidelity": "twin speedup / production speedup",
            "queries": [measure_query(prod_dsn, twin_dsn, qid, case) for qid, case in cfg("sandbox.fidelity_queries").items()]}


def main() -> None:
    doc = run(os.environ["PROD_DSN"], os.environ["TWIN_DSN"])
    path = cfg("sandbox.fidelity_path")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main()
