"""Plan generation runner (doc, "Data and training plan").

For each database and index setup: drop every non-primary index, create the setup's indexes,
then run every template x parameter set with EXPLAIN (ANALYZE, FORMAT JSON) twice, keeping
the second (warm cache). A run that hits statement_timeout is kept as the estimated plan
(plain EXPLAIN) labelled timed_out with runtime "at least" the timeout. Errors are recorded,
not dropped silently.

Output (config plan_generation.output_dir, gitignored except the sample):
  plans_raw.jsonl  one line per run, appended as runs finish; a rerun skips finished runs
  plans.jsonl      deduplicated by shape hash (dedupe())
  summary.json     counts per database and template, timeouts, errors, distinct shapes

One record:
  plan_uid, database, template_id, demo, param_set, setup_id, timeout_ms, timed_out,
  runtime_ms (null if timed out), shape_hash, plan (EXPLAIN JSON root object), error
The EXPLAIN ANALYZE JSON holds both estimated (Plan Rows, Total Cost) and actual (Actual
Rows, Actual Total Time) values per node, so one plan serves as estimated and actual plan.

Privacy: raw plans hold real table and column names and generated literals. They are
private-side data: only the tools/bench containers mount data/. A GNN featurizer must strip
names and literals before anything reaches the ai container.
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

from common.config import REPO_ROOT, cfg
from db.plangen import load, queries, quickmart_templates, setups

_conns: dict[str, psycopg.Connection] = {}


def out_dir() -> Path:
    d = REPO_ROOT / cfg("plan_generation.output_dir")
    d.mkdir(parents=True, exist_ok=True)
    return d


def plan_uid(database: str, template_id: str, param_set: int, setup_id: str) -> str:
    return hashlib.sha1(f"{database}|{template_id}|{param_set}|{setup_id}".encode()).hexdigest()[:16]


def shape_hash(plan_root: dict, bucket: float) -> str:
    """Hash of the plan tree: node type, join type, relation, index and log2(estimated rows)
    rounded to `bucket`. Same template with slightly different values and the same plan
    collapses; a different cardinality regime does not."""
    def walk(node: dict) -> list:
        rows = node.get("Plan Rows", 0)
        b = math.floor(math.log2(rows + 1) / bucket)
        return [node.get("Node Type"), node.get("Join Type"), node.get("Relation Name"),
                node.get("Index Name"), b, [walk(k) for k in node.get("Plans", [])]]
    return hashlib.sha1(json.dumps(walk(plan_root["Plan"])).encode()).hexdigest()[:16]


def workload() -> dict[str, dict]:
    """{database: {"templates": [(template_id, demo, [sql per param set])], "setups": {...}}}"""
    n = int(cfg("plan_generation.parameter_sets_per_query"))
    seed = int(cfg("dataset.random_seed"))
    dsb_index_sql = (Path(os.environ["DSB_HOME"]) / "scripts" / "dsb_index_pg.sql").read_text()
    return {
        "quickmart": {"templates": quickmart_templates.instances(n, seed), "setups": setups.QUICKMART},
        "tpch": {"templates": queries.tpch_instances(n, seed, int(cfg("plan_generation.tpch_scale_factor"))),
                 "setups": setups.TPCH},
        "dsb": {"templates": queries.dsb_instances(n, seed, int(cfg("plan_generation.dsb_scale_factor"))),
                "setups": setups.dsb_setups(dsb_index_sql, seed)},
    }


def check_setup_counts(wl: dict) -> None:
    lo, hi = int(cfg("plan_generation.index_setups_per_query_min")), int(cfg("plan_generation.index_setups_per_query_max"))
    for db, w in wl.items():
        assert lo <= len(w["setups"]) <= hi, (db, len(w["setups"]))


def apply_setup(database: str, statements: list[str]) -> None:
    with psycopg.connect(load.dsn_for(database), autocommit=True) as conn:
        drop = conn.execute("""SELECT i.indexrelid::regclass::text FROM pg_index i
                               JOIN pg_class c ON c.oid = i.indrelid
                               WHERE c.relnamespace = 'public'::regnamespace
                                 AND NOT i.indisprimary AND NOT i.indisunique""").fetchall()
        for (name,) in drop:
            conn.execute(f"DROP INDEX {name}")
        for stmt in statements:
            conn.execute(stmt)
        conn.execute("ANALYZE")


def _conn(database: str) -> psycopg.Connection:
    if database not in _conns:
        c = psycopg.connect(load.dsn_for(database), autocommit=True)
        c.execute(f"SET statement_timeout = '{int(cfg('postgres.statement_timeout_plan_generation_s'))}s'")
        _conns[database] = c
    return _conns[database]


def run_one(task: tuple) -> dict:
    database, template_id, demo, param_set, setup_id, sql = task
    rec = {"plan_uid": plan_uid(database, template_id, param_set, setup_id), "database": database,
           "template_id": template_id, "demo": demo, "param_set": param_set, "setup_id": setup_id,
           "timeout_ms": int(cfg("postgres.statement_timeout_plan_generation_s")) * 1000,
           "timed_out": False, "runtime_ms": None, "shape_hash": None, "plan": None, "error": None}
    conn = _conn(database)
    try:
        conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)      # warm-up run, discarded
        plan = conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql).fetchone()[0][0]
        rec["runtime_ms"] = plan["Execution Time"]
    except psycopg.errors.QueryCanceled:
        rec["timed_out"] = True
        try:
            plan = conn.execute("EXPLAIN (FORMAT JSON) " + sql).fetchone()[0][0]
        except psycopg.Error as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
            return rec
    except psycopg.Error as e:
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
        if conn.broken or conn.closed:
            _conns.pop(database, None)   # reconnect on the next task
        return rec
    rec["plan"] = plan
    rec["shape_hash"] = shape_hash(plan, float(cfg("plan_generation.shape_rows_log2_bucket")))
    return rec


def tasks_for(database: str, templates: list, setup_id: str, param_sets) -> list[tuple]:
    return [(database, tid, demo, i, setup_id, sqls[i]) for tid, demo, sqls in templates for i in param_sets]


def done_uids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {json.loads(line)["plan_uid"] for line in f if line.strip()}


def execute(plan: list[tuple[str, str, list[str], list[tuple]]], out: Path, log=print) -> None:
    """plan: [(database, setup_id, index statements, tasks)]. Appends records to `out`."""
    finished = done_uids(out)
    workers = int(cfg("plan_generation.workers"))
    t0 = time.perf_counter()
    total = sum(len(t) for *_, t in plan)
    count = len(finished)
    with open(out, "a", encoding="utf-8") as f:
        for database, setup_id, statements, tasks in plan:
            todo = [t for t in tasks if plan_uid(t[0], t[1], t[3], t[4]) not in finished]
            if not todo:
                continue
            log(f"{database} {setup_id}: {len(statements)} indexes, {len(todo)} runs")
            apply_setup(database, statements)
            with mp.get_context("spawn").Pool(workers) as pool:
                for rec in pool.imap_unordered(run_one, todo):
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    count += 1
                    if count % 100 == 0:
                        log(f"{count} of {total} runs after {time.perf_counter() - t0:.0f} s")
    log(f"done: {count} of {total} runs in {time.perf_counter() - t0:.0f} s")


def full_plan(wl: dict) -> list:
    n = range(int(cfg("plan_generation.parameter_sets_per_query")))
    return [(db, sid, stmts, tasks_for(db, w["templates"], sid, n))
            for db, w in wl.items() for sid, stmts in w["setups"].items()]


def sample_plan(wl: dict, size: int) -> list:
    """About `size` runs spread over every database and template: parameter sets 0 and 1
    under each database's first setup and parameter set 2 under its second, trimmed round
    robin across databases."""
    per_db = {}
    for db, w in wl.items():
        sids = list(w["setups"])
        per_db[db] = [(sids[0], tasks_for(db, w["templates"], sids[0], [0, 1])),
                      (sids[1], tasks_for(db, w["templates"], sids[1], [2]))]
    quota = {db: 0 for db in wl}
    remaining = size
    while remaining > 0 and any(quota[db] < sum(len(t) for _, t in per_db[db]) for db in wl):
        for db in wl:
            if remaining and quota[db] < sum(len(t) for _, t in per_db[db]):
                quota[db] += 1
                remaining -= 1
    out = []
    for db, groups in per_db.items():
        left = quota[db]
        flat = [(sid, t) for sid, ts in groups for t in ts]
        # Parameter set 0 of every template first, so a trimmed quota still covers every
        # template; then parameter set 1; then the second setup.
        first_setup = groups[0][0]
        flat.sort(key=lambda st: (0, st[1][3], st[1][1]) if st[0] == first_setup else (1, 0, st[1][1]))
        chosen = flat[:left]
        for sid, stmts in wl[db]["setups"].items():
            ts = [t for s, t in chosen if s == sid]
            if ts:
                out.append((db, sid, stmts, ts))
    return out


def dedupe(raw: Path, out: Path, summary_path: Path, log=print) -> dict:
    keep = int(cfg("plan_generation.max_copies_per_shape"))
    seen: Counter = Counter()
    stats = defaultdict(Counter)
    kept = 0
    first: dict[str, dict] = {}
    with open(raw, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            first.setdefault(rec["plan_uid"], rec)
    with open(out, "w", encoding="utf-8") as f:
        for rec in first.values():
            key = rec["database"]
            stats[key]["runs"] += 1
            if rec["error"]:
                stats[key]["errors"] += 1
                continue
            stats[key]["timed_out"] += rec["timed_out"]
            seen[rec["shape_hash"]] += 1
            if seen[rec["shape_hash"]] <= keep:
                f.write(json.dumps(rec) + "\n")
                kept += 1
                stats[key]["kept"] += 1
    summary = {"kept": kept, "target": int(cfg("plan_generation.target_plan_count")),
               "distinct_shapes": len(seen), "per_database": {k: dict(v) for k, v in stats.items()},
               "templates_per_database": dict(Counter(r["database"] for r in first.values()
                                                      if r["param_set"] == 0 and not r["error"]
                                                      and r["setup_id"].endswith("base")))}
    summary_path.write_text(json.dumps(summary, indent=2))
    log(json.dumps(summary, indent=2))
    return summary
