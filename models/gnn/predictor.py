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

TODO(GNN): replace CostPredictor with the trained model from models/gnn behind the same
fit()/predict() interface; Prediction.estimator becomes "gnn".
"""
from __future__ import annotations

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
            "estimator": ESTIMATOR,
            "total_ms": round(total_cost * self.ms_per_cost, 3),
            "nodes": [{"node_id": nid, "self_ms": round(c * self.ms_per_cost, 3), "share": round(c / denom, 4)}
                      for nid, c in sorted(own.items())],
        }


def predict(plan: dict, predictor: CostPredictor) -> dict:
    """The interface the RL search and the LLM tools call."""
    return predictor.predict(plan)
