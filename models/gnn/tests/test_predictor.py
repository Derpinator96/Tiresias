"""Predictor tests. Unit tests on synthetic plans; one component test on the live Q1 plan."""
import os

import httpx
import pytest

from agent.api import predict_plans
from contracts.validate import errors
from models.gnn.predictor import ESTIMATOR, CostPredictor, NotCalibrated, predict

T = "t_aaaaaaaa"


def plan(plan_id, source, nodes):
    return {"plan_id": plan_id, "template_id": "q_00000001", "setup_id": "s_baseline", "source": source, "nodes": nodes}


MEASURED = plan("p_00000001", "auto_explain", [
    {"node_id": 0, "parent_id": None, "op": "Aggregate", "est_rows": 1, "est_cost": 1000, "width": 32, "actual_rows": 1, "self_ms": 1.0},
    {"node_id": 1, "parent_id": 0, "op": "Seq Scan", "relation": T, "est_rows": 2000, "est_cost": 990, "width": 8, "actual_rows": 2000, "self_ms": 19.0},
])
HYPO = plan("p_00000002", "hypopg", [
    {"node_id": 0, "parent_id": None, "op": "Aggregate", "est_rows": 1, "est_cost": 100, "width": 32},
    {"node_id": 1, "parent_id": 0, "op": "Bitmap Heap Scan", "relation": T, "est_rows": 2000, "est_cost": 90, "width": 8},
    {"node_id": 2, "parent_id": 1, "op": "Bitmap Index Scan", "index": "i_00000001", "est_rows": 2000, "est_cost": 30, "width": 0},
])


def test_calibration_comes_from_measurement():
    m = CostPredictor().fit([MEASURED])
    assert m.ms_per_cost == pytest.approx(20.0 / 1000)
    assert m.calibrated_on == ["p_00000001"]


def test_unmeasured_plans_cannot_calibrate():
    with pytest.raises(NotCalibrated):
        CostPredictor().fit([HYPO])
    with pytest.raises(NotCalibrated):
        CostPredictor().predict(HYPO)


def test_prediction_shape_and_shares():
    p = predict(HYPO, CostPredictor().fit([MEASURED]))
    assert errors("Prediction", p) == []
    assert p["estimator"] == ESTIMATOR
    assert p["total_ms"] == pytest.approx(100 * 0.02)
    shares = {n["node_id"]: n["share"] for n in p["nodes"]}
    assert sum(shares.values()) == pytest.approx(1.0, abs=1e-3)
    # Own costs: aggregate 10, heap 60, index 30.
    assert shares[1] == pytest.approx(0.6) and shares[2] == pytest.approx(0.3)


def test_live_q1_seq_scan_is_the_bottleneck():
    """Component: the latest Q1 auto_explain plan from the gateway (run in tools after make seed)."""
    base = os.environ["GATEWAY_URL"]
    slow = httpx.get(base + "/v1/templates/slow", timeout=30).json()
    plans = httpx.get(f"{base}/v1/templates/{slow[0]['template_id']}/plans", timeout=30).json()
    out = predict_plans([plans[0]])[0]
    top = max(out["nodes"], key=lambda n: n["share"])
    op = {n["node_id"]: n["op"] for n in plans[0]["nodes"]}[top["node_id"]]
    assert op == "Seq Scan"
    assert top["share"] > 0.5
