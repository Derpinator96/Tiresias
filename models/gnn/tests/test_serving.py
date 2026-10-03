"""Serving checks (no database): GNNPredictor output is a valid Prediction, and
load_predictor() serves the GNN only when its scored results beat the Postgres baseline."""
import json

import numpy as np
import pytest

from contracts.validate import validate
from models.gnn import predictor as pred
from models.gnn import train
from models.gnn.tests.test_gnn import dataset  # noqa: F401  (shared synthetic dataset fixture)

PLAN = {"plan_id": "p_0000abcd", "template_id": "q_0000abcd", "setup_id": "s_baseline", "source": "explain",
        "nodes": [{"node_id": 0, "parent_id": None, "op": "Aggregate", "est_rows": 1, "est_cost": 17000, "width": 8},
                  {"node_id": 1, "parent_id": 0, "op": "Seq Scan", "relation": "t_0123abcd", "est_rows": 2400,
                   "est_cost": 16000, "width": 10, "filter_cols": ["c_0123abcd", "c_4567abcd"]}]}


@pytest.fixture(scope="module")
def weights(dataset, tmp_path_factory):   # noqa: F811
    w = tmp_path_factory.mktemp("w")
    train.train(dataset, w, log=lambda m: None)
    return w


def results(tmp_path, gnn_q, pg_q):
    p = tmp_path / "results.json"
    p.write_text(json.dumps({"models": {"gnn": {"median_q_error": gnn_q}, "postgres": {"median_q_error": pg_q}}}))
    return p


def test_gnn_prediction_is_valid(weights):
    out = pred.GNNPredictor(weights).predict(PLAN)
    validate("Prediction", out)
    assert out["estimator"] == "gnn" and np.isclose(sum(n["share"] for n in out["nodes"]), 1.0, atol=1e-3)


def test_gnn_served_only_when_it_wins(weights, tmp_path):
    assert isinstance(pred.load_predictor(weights, results(tmp_path, 1.4, 3.0)), pred.GNNPredictor)
    assert isinstance(pred.load_predictor(weights, results(tmp_path, 3.5, 3.0)), pred.CostPredictor)
    assert isinstance(pred.load_predictor(tmp_path / "none", results(tmp_path, 1.4, 3.0)), pred.CostPredictor)


def test_label_carries_the_scored_number(weights, tmp_path):
    p = pred.load_predictor(weights, results(tmp_path, 1.4, 3.0))
    assert "median q-error 1.4 on unseen templates" in p.label
