"""GNN node features from HashedPlan nodes. One code path for export, training, evaluation
and serving, so the model sees in production exactly what it saw in training.

strip() reduces a HashedPlan node (codes, filter text) to numbers and the operator name.
The training export stores only stripped nodes, so the dataset holds no names, no codes and
no literals and may leave the machine.

Feature set v1 (FEATURE_VERSION): op one-hot over the contract's plan_node_type enum,
log1p of est_rows, est_cost, own est cost (est_cost minus children's) and width, has_index,
n_filter_cols, filter_redacted. The doc also lists role bits and table rows; HashedPlan
nodes do not carry them (they live in ColumnMeta and TableMeta), so v1 leaves them out
(labelled deviation, db/NOTES.md and models/gnn/NOTES.md).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

FEATURE_VERSION = 1
_COMMON = Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "common.schema.json"
OPS: list[str] = json.loads(_COMMON.read_text())["$defs"]["plan_node_type"]["enum"]
_OP_INDEX = {op: i for i, op in enumerate(OPS)}
NUMERIC = ["log_est_rows", "log_est_cost", "log_own_cost", "log_width", "has_index", "n_filter_cols", "filter_redacted"]
N_FEATURES = len(OPS) + len(NUMERIC)


def strip(node: dict) -> dict:
    """HashedPlan node -> the fields the model may see (plus labels when the plan ran)."""
    out = {"op": node["op"], "parent": node["parent_id"], "est_rows": node["est_rows"],
           "est_cost": node["est_cost"], "width": node["width"],
           "has_index": int("index" in node), "n_filter_cols": len(node.get("filter_cols", [])),
           "filter_redacted": int(bool(node.get("filter_redacted")))}
    for k in ("self_ms", "actual_rows"):
        if k in node:
            out[k] = node[k]
    return out


def parents(nodes: list[dict]) -> np.ndarray:
    """Parent index per node, -1 for the root. Nodes are in preorder (hash_plan's order)."""
    return np.array([-1 if n["parent"] is None else n["parent"] for n in nodes], dtype=np.int64)


def node_features(nodes: list[dict]) -> np.ndarray:
    par = parents(nodes)
    child_cost = np.zeros(len(nodes))
    np.add.at(child_cost, par[par >= 0], [nodes[i]["est_cost"] for i in np.where(par >= 0)[0]])
    x = np.zeros((len(nodes), N_FEATURES), dtype=np.float32)
    for i, n in enumerate(nodes):
        x[i, _OP_INDEX[n["op"]]] = 1.0
        x[i, len(OPS):] = [np.log1p(n["est_rows"]), np.log1p(n["est_cost"]),
                           np.log1p(max(0.0, n["est_cost"] - child_cost[i])), np.log1p(n["width"]),
                           n["has_index"], n["n_filter_cols"], n["filter_redacted"]]
    return x


def targets(nodes: list[dict]) -> np.ndarray:
    """log1p(self_ms) per node; NaN where the plan did not run."""
    return np.array([np.log1p(n["self_ms"]) if "self_ms" in n else np.nan for n in nodes], dtype=np.float32)


def plan_features(nodes: list[dict]) -> np.ndarray:
    """Plan-level features for the gradient-boosted baseline (doc: counts per operator type
    plus sums of the log features over the plan)."""
    x = node_features(nodes)
    return np.concatenate([x[:, :len(OPS)].sum(0), x[:, len(OPS):].sum(0), x[0, len(OPS):]])
