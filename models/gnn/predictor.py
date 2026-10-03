"""Runtime predictor: predict(HashedPlan) -> Prediction.

SIMPLIFIED for the walking skeleton. The GNN is not built yet. This estimator uses
Postgres's own cost estimates, converted to milliseconds with one ratio measured at run time:

    ms_per_cost = sum of measured self_ms / root est_cost, over plans that actually ran

It is never a hardcoded constant. Each node's own cost is its total cost minus its
children's (Postgres costs are cumulative), and its predicted share is its own cost over the
root cost. On-screen label: LABEL below.

Known weakness, which is why the doc calls for a GNN: one ratio, calibrated on a sequential
scan, is applied to index scans too, and Postgres's cost units do not scale the same way
across operators.

GNNPredictor serves the trained model (models/gnn/weights) behind the same fit()/predict()
interface. load_predictor() picks it only when models/gnn/results.json shows it beats this
calibrated baseline on unseen templates (doc: "use the better one"); otherwise it returns
CostPredictor, so the label on screen always names the estimator actually serving.
"""
from __future__ import annotations

import json
from pathlib import Path

ESTIMATOR = "postgres_cost_calibrated"
LABEL = "estimator: Postgres cost x calibration (GNN pending)"


class NotCalibrated(RuntimeError):
    pass


def _children(plan: dict) -> dict[int, list[dict]]:
    kids: dict[int, list[dict]] = {}
    for n in plan["nodes"]:
        if n["parent_id"] is not None:
            kids.setdefault(n["parent_id"], []).append(n)
    return kids


def _self_costs(plan: dict) -> dict[int, float]:
    kids = _children(plan)
    return {n["node_id"]: max(0.0, n["est_cost"] - sum(k["est_cost"] for k in kids.get(n["node_id"], [])))
            for n in plan["nodes"]}


def _root(plan: dict) -> dict:
    return next(n for n in plan["nodes"] if n["parent_id"] is None)


class CostPredictor:
    estimator = ESTIMATOR
    label = LABEL
    needs_calibration = True

    def __init__(self) -> None:
        self.ms_per_cost: float | None = None
        self.calibrated_on: list[str] = []

    def fit(self, measured_plans: list[dict]) -> "CostPredictor":
        """Calibrate on plans that ran (they carry self_ms)."""
        ran = [p for p in measured_plans if all("self_ms" in n for n in p["nodes"])]
        cost = sum(_root(p)["est_cost"] for p in ran)
        if not ran or cost <= 0:
            raise NotCalibrated("no measured plan to calibrate on")
        self.ms_per_cost = sum(n["self_ms"] for p in ran for n in p["nodes"]) / cost
        self.calibrated_on = [p["plan_id"] for p in ran]
        return self

    def predict(self, plan: dict) -> dict:
        if self.ms_per_cost is None:
            raise NotCalibrated("call fit() with a measured plan first")
        own = _self_costs(plan)
        total_cost = _root(plan)["est_cost"]
        denom = sum(own.values()) or 1.0
        return {
            "plan_id": plan["plan_id"],
            "estimator": self.estimator,
            "total_ms": round(total_cost * self.ms_per_cost, 3),
            "nodes": [{"node_id": nid, "self_ms": round(c * self.ms_per_cost, 3), "share": round(c / denom, 4)}
                      for nid, c in sorted(own.items())],
        }


def predict(plan: dict, predictor: CostPredictor) -> dict:
    """The interface the RL search and the LLM tools call."""
    return predictor.predict(plan)


HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "weights"
RESULTS = HERE / "results.json"


class GNNPredictor:
    estimator = "gnn"
    needs_calibration = False

    def __init__(self, weights_dir: Path = WEIGHTS, results: dict | None = None):
        import torch
        from models.gnn import features
        from models.gnn.model import PlanGNN
        meta = json.loads((weights_dir / "meta.json").read_text())
        if meta["feature_version"] != features.FEATURE_VERSION:
            raise ValueError(f"weights use feature version {meta['feature_version']}, code has {features.FEATURE_VERSION}")
        self.model = PlanGNN(meta["n_features"], meta["hidden_size"], meta["layers"], meta["dropout"])
        self.model.load_state_dict(torch.load(weights_dir / "gnn.pt", map_location="cpu"))
        self.model.eval()
        q = (results or {}).get("models", {}).get("gnn", {}).get("median_q_error")
        self.label = "estimator: GNN" + (f", median q-error {q} on unseen templates (models/gnn/results.json)" if q else "")

    def fit(self, measured_plans: list[dict]) -> "GNNPredictor":
        return self   # trained offline; nothing to calibrate at run time

    def predict(self, plan: dict) -> dict:
        import numpy as np
        import torch
        from models.gnn import features
        from models.gnn.model import batch
        assert [n["node_id"] for n in plan["nodes"]] == list(range(len(plan["nodes"]))), "nodes must be in preorder"
        nodes = [features.strip(n) for n in plan["nodes"]]
        with torch.no_grad():
            x, p, _ = batch([(features.node_features(nodes), features.parents(nodes))])
            ms = np.expm1(self.model(x, p).numpy()).clip(min=0).astype(float)
        total = float(ms.sum()) or 1.0
        return {"plan_id": plan["plan_id"], "estimator": self.estimator, "total_ms": round(float(ms.sum()), 3),
                "nodes": [{"node_id": i, "self_ms": round(float(m), 3), "share": round(float(m) / total, 4)}
                          for i, m in enumerate(ms)]}


def load_predictor(weights_dir: Path = WEIGHTS, results_path: Path = RESULTS):
    """The GNN when its scored results beat the calibrated Postgres baseline, else CostPredictor."""
    if (weights_dir / "gnn.pt").exists() and results_path.exists():
        res = json.loads(results_path.read_text())
        m = res.get("models", {})
        if "gnn" in m and m["gnn"]["median_q_error"] < m["postgres"]["median_q_error"]:
            return GNNPredictor(weights_dir, res)
    return CostPredictor()
