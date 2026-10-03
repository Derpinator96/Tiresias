"""Plans from the auto_explain JSON log, hashed into HashedPlan objects.

The log is PostgreSQL jsonlog (one JSON object per line). auto_explain entries have a
`message` of the form "duration: N ms  plan:\\n{plan JSON}" and a `query_id` equal to
pg_stat_statements' queryid, which ties each plan to its template.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

from common.config import cfg
from gateway.hashing import Hasher
from gateway.rounding import round_count, round_sig
from gateway.strip import Unparsed, hash_filter

CONDITION_KEYS = ("Filter", "Index Cond", "Recheck Cond", "Join Filter", "Hash Cond", "Merge Cond")


@dataclass
class LoggedPlan:
    """Private record. `query_text` holds real literals and never leaves the gateway."""
    query_id: int
    query_text: str
    plan: dict
    order_key: tuple


def read_log(log_dir: str) -> list[LoggedPlan]:
    role = cfg("workload.app_role")
    out = []
    for path in sorted(glob.glob(os.path.join(log_dir, "*.json"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message", "")
                if rec.get("user") != role or "plan:" not in msg or not rec.get("query_id"):
                    continue
                try:
                    plan = json.loads(msg.split("plan:", 1)[1])
                except json.JSONDecodeError:
                    continue
                out.append(LoggedPlan(int(rec["query_id"]), plan.get("Query Text", ""), plan,
                                      (rec.get("timestamp", ""), rec.get("session_id", ""), rec.get("line_num", 0))))
    out.sort(key=lambda p: p.order_key)
    return out


def _alias_map(node: dict, acc: dict[str, str]) -> dict[str, str]:
    if "Relation Name" in node:
        acc[node.get("Alias", node["Relation Name"])] = node["Relation Name"]
        acc[node["Relation Name"]] = node["Relation Name"]
    for child in node.get("Plans", []):
        _alias_map(child, acc)
    return acc


def hash_plan(plan_json: dict, *, plan_id: str, template_id: str, setup_id: str, source: str,
              hasher: Hasher, schema: dict[str, set[str]]) -> dict:
    """Turn one EXPLAIN (FORMAT JSON) plan into a HashedPlan. Measured fields are included
    only when the plan ran (it has Actual Total Time)."""
    root = plan_json["Plan"]
    aliases = _alias_map(root, {})
    nodes: list[dict] = []

    def walk(node: dict, parent: int | None, in_gather: bool) -> float:
        node_id = len(nodes)
        relation = node.get("Relation Name")
        out = {"node_id": node_id, "parent_id": parent, "op": node["Node Type"]}
        if relation:
            out["relation"] = hasher.table(relation)
        if "Index Name" in node:
            out["index"] = hasher.index(node["Index Name"])
        parts, cols, redacted = [], [], False
        for key in CONDITION_KEYS:
            if key in node:
                try:
                    text, c = hash_filter(node[key], hasher, schema, aliases, relation)
                    parts.append(text)
                    cols += [x for x in c if x not in cols]
                except Unparsed:
                    redacted = True
        if cols:
            out["filter_cols"] = cols
        if parts:
            out["filter"] = " AND ".join(parts)
        if redacted:
            out["filter_redacted"] = True
        out.update({"est_rows": round_count(node["Plan Rows"]), "est_cost": round_sig(node["Total Cost"]),
                    "width": int(node["Plan Width"])})
        nodes.append(out)

        ran = "Actual Total Time" in node
        loops = node.get("Actual Loops", 1) or 1
        parallel = in_gather or node.get("Parallel Aware", False)
        # Parallel workers overlap in time, so their per-loop time is already wall time.
        total = node.get("Actual Total Time", 0.0) * (1 if parallel else loops)
        child_gather = in_gather or node["Node Type"] in ("Gather", "Gather Merge")
        children_total = sum(walk(ch, node_id, child_gather) for ch in node.get("Plans", []))
        if ran:
            out["actual_rows"] = round_count(node.get("Actual Rows", 0) * loops)
            removed = node.get("Rows Removed by Filter", 0) + node.get("Rows Removed by Index Recheck", 0)
            if removed:
                out["rows_removed"] = round_count(removed * loops)
            out["self_ms"] = round(max(0.0, total - children_total), 3)
        return total

    walk(root, None, False)
    return {"plan_id": plan_id, "template_id": template_id, "setup_id": setup_id,
            "source": source, "nodes": nodes}
