"""Write data/plans/web_sample.json: one entry per (database, template_id) of the plan-generation
workload, with the parameter-set-0 query text and statistics over the kept plans in plans.jsonl.

Read at runtime by the local web app's /slow-log page (BT_PLANS_SAMPLE). The file holds real table
and column names and benchmark SQL, so it lives under data/ and never under site/web/src.

Runs in the bench container (make's BENCH), where DSB_HOME and TPCH_HOME exist:
  docker compose ... --profile bench run --rm -T bench python -m scripts.plans_web_sample
Without the kits (KeyError or a generator failure) only the QuickMart templates are written and
the file says so in "note".
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from common.config import REPO_ROOT, cfg

TOP_OPS = 3


def node_count(node: dict) -> int:
    return 1 + sum(node_count(k) for k in node.get("Plans", []))


def node_types(node: dict) -> Iterable[str]:
    """Node types root to leaf, depth first."""
    yield node["Node Type"]
    for k in node.get("Plans", []):
        yield from node_types(k)


def aggregate(plans: Iterable[dict], templates: dict[tuple[str, str], tuple[str, bool]]) -> list[dict]:
    """One entry per template. `plans`: kept plan records (plans.jsonl lines, streamed once).
    `templates`: {(database, template_id): (parameter-set-0 SQL, demo)}. Templates that have no
    kept plan still get an entry with plans 0 and null runtimes; a plan whose template is not in
    `templates` (an old or renamed one) gets an entry with sql null."""
    stats: dict[tuple[str, str], dict] = defaultdict(lambda: {"runtimes": [], "timed_out": 0, "ops": Counter(), "nodes": None})
    for rec in plans:
        s = stats[(rec["database"], rec["template_id"])]
        if rec["timed_out"]:
            s["timed_out"] += 1
        elif rec["runtime_ms"] is not None:
            s["runtimes"].append(rec["runtime_ms"])
        root = (rec.get("plan") or {}).get("Plan")
        if root:
            s["ops"].update(node_types(root))
            if s["nodes"] is None:
                s["nodes"] = node_count(root)
    out = []
    for key in sorted(set(templates) | set(stats)):
        s = stats.get(key) or {"runtimes": [], "timed_out": 0, "ops": Counter(), "nodes": None}
        sql, demo = templates.get(key, (None, False))
        rt = s["runtimes"]
        out.append({
            "database": key[0], "template_id": key[1], "demo": demo, "sql": sql,
            "plans": len(rt) + s["timed_out"],
            "median_runtime_ms": round(statistics.median(rt), 3) if rt else None,
            "max_runtime_ms": round(max(rt), 3) if rt else None,
            "timed_out": s["timed_out"],
            "nodes": s["nodes"],
            "top_ops": [op for op, _ in s["ops"].most_common(TOP_OPS)],
        })
    return out


def read_plans(path: Path) -> Iterable[dict]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def workload_templates() -> tuple[dict[tuple[str, str], tuple[str, bool]], str]:
    """Parameter-set-0 SQL per template, and a note when only QuickMart could be generated."""
    from db.plangen import run
    try:
        wl = run.workload()
        note = ""
    except Exception as e:  # DSB_HOME/TPCH_HOME unset or dsqgen/qgen missing: QuickMart only
        from db.plangen import load, quickmart_templates
        n, seed = int(cfg("plan_generation.parameter_sets_per_query")), int(cfg("dataset.random_seed"))
        wl = {db: {"templates": quickmart_templates.instances(n, seed, rows)} for db, rows in load.quickmart_databases().items()}
        note = f"QuickMart templates only: the benchmark kits could not generate ({type(e).__name__}: {e})"[:300]
    return {(db, tid): (sqls[0], demo) for db, w in wl.items() for tid, demo, sqls in w["templates"]}, note


def main() -> int:
    plans = REPO_ROOT / cfg("plan_generation.output_dir") / "plans.jsonl"
    out = plans.with_name("web_sample.json")
    templates, note = workload_templates()
    entries = aggregate(read_plans(plans) if plans.exists() else [], templates)
    doc = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "plans_file": str(plans.relative_to(REPO_ROOT)), "plans_present": plans.exists(),
           "note": note or "plan generation workload (data/plans), not pg-prod's log; sql is parameter set 0; "
                           "top_ops counts node types over every kept plan of the template, nodes is one kept plan",
           "entries": entries}
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"{out.relative_to(REPO_ROOT)}: {len(entries)} templates, {sum(e['plans'] for e in entries)} plans"
          + (f"; {note}" if note else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
