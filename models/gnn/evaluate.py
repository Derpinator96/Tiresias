"""Score runtime predictors on held-out templates (doc, "Evaluation and metrics"). The
trainer never grades their own model: this harness scores the GNN and both baselines the
same way, on test groups from split.json that no model trained on.

Metrics (test plans that ran; timed-out plans are counted, not scored):
- q-error of total runtime, median and 95th percentile (q = max(pred/actual, actual/pred));
- pairwise ranking accuracy: same template and parameters under different index setups,
  does the predictor order the two plans like the measured runtimes?
- bottleneck match: is the node with the largest predicted self time the measured one?
Baselines: "postgres": the existing CostPredictor fit on the training split; "gbt":
scikit-learn HistGradientBoostingRegressor on plan_features, standing in for XGBoost
(human decision 2026-10-03).

    python -m models.gnn.evaluate [dataset_dir] [weights_dir]   -> models/gnn/results.json
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from common.config import REPO_ROOT, cfg
from models.gnn import features
from models.gnn.predictor import CostPredictor
from models.gnn.train import load

RESULTS = REPO_ROOT / "models" / "gnn" / "results.json"


def q_errors(pred: np.ndarray, actual: np.ndarray) -> np.ndarray:
    pred, actual = np.maximum(pred, 1e-3), np.maximum(actual, 1e-3)   # 1 microsecond floor
    return np.maximum(pred / actual, actual / pred)


def ranking_accuracy(rows: list[dict], pred: np.ndarray) -> tuple[float | None, int]:
    by_query = defaultdict(list)
    for i, r in enumerate(rows):
        by_query[(r["group"], r["param_set"])].append(i)
    hits = pairs = 0
    for idx in by_query.values():
        for a, b in itertools.combinations(idx, 2):
            if rows[a]["total_ms"] != rows[b]["total_ms"]:
                pairs += 1
                hits += (pred[a] < pred[b]) == (rows[a]["total_ms"] < rows[b]["total_ms"])
    return (hits / pairs if pairs else None), pairs


def bottleneck_match(rows: list[dict], node_preds: list[np.ndarray]) -> float:
    hits = [int(np.argmax(p) == np.nanargmax(np.expm1(features.targets(r["nodes"]))))
            for r, p in zip(rows, node_preds)]
    return float(np.mean(hits))


def summarize(rows, total_pred, node_preds=None) -> dict:
    q = q_errors(np.asarray(total_pred), np.array([r["total_ms"] for r in rows]))
    acc, pairs = ranking_accuracy(rows, np.asarray(total_pred))
    out = {"median_q_error": round(float(np.median(q)), 3), "p95_q_error": round(float(np.percentile(q, 95)), 3),
           "ranking_accuracy": None if acc is None else round(acc, 3), "ranking_pairs": pairs}
    if node_preds is not None:
        out["bottleneck_match"] = round(bottleneck_match(rows, node_preds), 3)
    return out


def as_hashed(r: dict, i: int) -> dict:
    """Stripped nodes back into the HashedPlan shape CostPredictor reads."""
    return {"plan_id": f"p_{i:08x}", "nodes": [{"node_id": j, "parent_id": n["parent"], "est_cost": n["est_cost"],
                                               **({"self_ms": n["self_ms"]} if "self_ms" in n else {})}
                                              for j, n in enumerate(r["nodes"])]}


def postgres_baseline(train_rows, test_rows):
    model = CostPredictor().fit([as_hashed(r, i) for i, r in enumerate(train_rows)])
    preds = [model.predict(as_hashed(r, i)) for i, r in enumerate(test_rows)]
    return [p["total_ms"] for p in preds], [np.array([n["self_ms"] for n in p["nodes"]]) for p in preds]


def gbt_baseline(train_rows, test_rows):
    X = np.stack([features.plan_features(r["nodes"]) for r in train_rows])
    y = np.log1p([r["total_ms"] for r in train_rows])
    m = HistGradientBoostingRegressor(random_state=int(cfg("dataset.random_seed"))).fit(X, y)
    return list(np.expm1(m.predict(np.stack([features.plan_features(r["nodes"]) for r in test_rows]))))


def gnn_predictions(weights_dir: Path, test_rows):
    import torch
    from models.gnn.model import PlanGNN, batch
    meta = json.loads((weights_dir / "meta.json").read_text())
    if meta["feature_version"] != features.FEATURE_VERSION:
        raise ValueError(f"weights use feature version {meta['feature_version']}, code has {features.FEATURE_VERSION}")
    model = PlanGNN(meta["n_features"], meta["hidden_size"], meta["layers"], meta["dropout"])
    model.load_state_dict(torch.load(weights_dir / "gnn.pt", map_location="cpu"))
    model.eval()
    node_preds = []
    with torch.no_grad():
        for r in test_rows:
            x, p, _ = batch([(features.node_features(r["nodes"]), features.parents(r["nodes"]))])
            node_preds.append(np.expm1(model(x, p).numpy()).clip(min=0))
    return [float(n.sum()) for n in node_preds], node_preds, meta


def evaluate(dataset_dir: Path, weights_dir: Path | None) -> dict:
    ran = lambda rows: [r for r in rows if not r["timed_out"] and r["total_ms"] is not None]
    train_all, test_all = load(dataset_dir, "train"), load(dataset_dir, "test")
    train, test = ran(train_all), ran(test_all)
    pg_total, pg_nodes = postgres_baseline(train, test)
    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "feature_version": features.FEATURE_VERSION,
        "test_plans_scored": len(test), "test_plans_timed_out": len(test_all) - len(test),
        "test_groups": len({r["group"] for r in test_all}), "train_plans": len(train),
        "assumptions": [
            "test templates were never seen in training (split.json, by template)",
            "timed-out plans (runtime at least the statement timeout) are counted, not scored",
            "runtimes measured with concurrent plan-generation workers, so they carry noise",
            "gbt is scikit-learn HistGradientBoosting standing in for XGBoost",
        ],
        "models": {"postgres": summarize(test, pg_total, pg_nodes), "gbt": summarize(test, gbt_baseline(train, test))},
    }
    if weights_dir and (weights_dir / "gnn.pt").exists():
        total, nodes, meta = gnn_predictions(weights_dir, test)
        results["models"]["gnn"] = summarize(test, total, nodes)
        results["gnn_meta"] = meta
    return results


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / cfg("gnn.dataset_dir")
    w = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / "models" / "gnn" / "weights"
    res = evaluate(d, w)
    RESULTS.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
