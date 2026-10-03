"""Model, reference training and evaluation harness checks on synthetic data (no database).
Run in the tools container (make test-predictor) or anywhere with torch and scikit-learn."""
import gzip
import json

import numpy as np
import pytest
import torch

from db.plangen import export
from models.gnn import evaluate, features, train
from models.gnn.model import PlanGNN, batch


def plan(rng, scale):
    """Aggregate over a seq scan; the scan's self time grows with its estimated cost."""
    cost = float(rng.uniform(100, 100000)) * scale
    scan_ms = cost / 1000
    return [{"op": "Aggregate", "parent": None, "est_rows": 1, "est_cost": cost * 1.01, "width": 8, "has_index": 0,
             "n_filter_cols": 0, "filter_redacted": 0, "self_ms": scan_ms * 0.05},
            {"op": "Seq Scan", "parent": 0, "est_rows": 1000, "est_cost": cost, "width": 8, "has_index": 0,
             "n_filter_cols": 2, "filter_redacted": 0, "self_ms": scan_ms}]


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = tmp_path_factory.mktemp("gnn")
    rng = np.random.default_rng(0)
    rows, groups = [], {}
    for g in range(30):
        key = f"g_{g:012x}"
        groups[key] = False
        for p in range(4):
            for s, scale in enumerate((1.0, 0.1)):   # setup 1 is 10x cheaper, like an index
                nodes = plan(rng, scale)
                rows.append({"group": key, "database": "tpch", "demo": False, "setup": s, "param_set": p,
                             "timed_out": False, "total_ms": sum(n["self_ms"] for n in nodes), "nodes": nodes})
    with gzip.open(d / "dataset.jsonl.gz", "wt") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    (d / "split.json").write_text(json.dumps(export.make_split(groups, 1)))
    return d


def test_batch_has_no_cross_graph_leakage():
    torch.manual_seed(0)
    m = PlanGNN(features.N_FEATURES, 16, 3, 0.0).eval()
    rng = np.random.default_rng(1)
    g1 = (features.node_features(plan(rng, 1)), np.array([-1, 0]))
    g2 = (features.node_features(plan(rng, 1) + plan(rng, 1)[1:]), np.array([-1, 0, 0]))
    x, p, _ = batch([g1, g2])
    together = m(x, p)
    alone = torch.cat([m(*batch([g])[:2]) for g in (g1, g2)])
    assert torch.allclose(together, alone, atol=1e-5)


def test_q_error_and_ranking_by_hand():
    assert evaluate.q_errors(np.array([2.0, 1.0]), np.array([1.0, 4.0])).tolist() == [2.0, 4.0]
    rows = [{"group": "g", "param_set": 0, "total_ms": 10.0}, {"group": "g", "param_set": 0, "total_ms": 1.0},
            {"group": "g", "param_set": 0, "total_ms": 5.0}]
    acc, pairs = evaluate.ranking_accuracy(rows, np.array([9.0, 2.0, 1.0]))   # (0,1) ok (0,2) ok (1,2) wrong
    assert pairs == 3 and acc == pytest.approx(2 / 3)


def test_reference_training_and_evaluation(dataset, tmp_path):
    meta = train.train(dataset, tmp_path, log=lambda m: None)
    assert meta["feature_version"] == features.FEATURE_VERSION and meta["trained_on_plans"] > 0
    res = evaluate.evaluate(dataset, tmp_path)
    assert set(res["models"]) == {"postgres", "gbt", "gnn"}
    gnn = res["models"]["gnn"]
    assert gnn["median_q_error"] < 2.0 and gnn["bottleneck_match"] == 1.0 and gnn["ranking_accuracy"] > 0.9


def test_feature_version_mismatch_refused(dataset, tmp_path):
    train.train(dataset, tmp_path, log=lambda m: None)
    meta = json.loads((tmp_path / "meta.json").read_text())
    (tmp_path / "meta.json").write_text(json.dumps({**meta, "feature_version": 0}))
    with pytest.raises(ValueError):
        evaluate.evaluate(dataset, tmp_path)
