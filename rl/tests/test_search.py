"""Greedy search tests. Unit tests use a fake gateway with known costs; the component test
runs the real search against the live gateway and HypoPG (tools container, after make seed)."""
import os

import httpx
import pytest

from common.config import cfg
from contracts.validate import errors
from models.gnn.predictor import CostPredictor
from rl import search

T = "t_aaaaaaaa"
A, B, C = "c_00000001", "c_00000002", "c_00000003"
CANDS = [
    {"cand_id": "cand_000000ab", "table": T, "columns": [A, B], "support": 1.0, "evidence": {"items": [f"{A}:EQ"], "templates": ["q_00000001"]}},
    {"cand_id": "cand_000000a0", "table": T, "columns": [A], "support": 1.0, "evidence": {"items": [f"{A}:EQ"], "templates": ["q_00000001"]}},
    {"cand_id": "cand_000000c0", "table": T, "columns": [C], "support": 1.0, "evidence": {"items": [f"{C}:EQ"], "templates": ["q_00000001"]}},
]
# Root est_cost per set of chosen column lists, and index MB per index.
COST = {(): 1000, ((A, B),): 100, ((A,),): 400, ((C,),): 990}
MB = {(A, B): 2.0, (A,): 1.0, (C,): 1.0}


def fake_post(calls):
    def post(path, body):
        assert path == "/v1/simulate/hypopg"
        key = tuple(sorted(tuple(a["columns"]) for a in body["actions"]))
        calls.append(key)
        # Combinations are no better than their best single index.
        cost = COST[key] if key in COST else min(COST[(k,)] for k in key)
        plan = {"plan_id": "p_00000009", "template_id": "q_00000001", "setup_id": "s_x", "source": "hypopg",
                "nodes": [{"node_id": 0, "parent_id": None, "op": "Seq Scan", "est_rows": 1, "est_cost": cost, "width": 8}]}
        return {"plans": [plan], "index_storage_mb": sum(MB[k] for k in key)}
    return post


@pytest.fixture
def searcher(monkeypatch):
    calls = []
    monkeypatch.setattr(search.gw, "post", fake_post(calls))
    model = CostPredictor()
    model.ms_per_cost = 0.02
    tpl = [{"template_id": "q_00000001", "calls": 10, "total_ms": 200.0, "columns": []}]
    s = search.GreedySearch(tpl, [], [{"table": T, "size_mb": 100.0}], model)
    s.calls = calls
    return s


def test_picks_the_best_candidate_and_stops(searcher):
    config = searcher.run(CANDS)
    assert errors("Config", config) == []
    assert [a["columns"] for a in config["actions"]] == [[A, B]]
    assert config["search"] == "greedy"
    step = searcher.trace.steps[0]
    assert step["predicted_ms_before"] == pytest.approx(20.0) and step["predicted_ms_after"] == pytest.approx(2.0)


def test_contribution_is_predicted_saving(searcher):
    action = searcher.run(CANDS)["actions"][0]
    assert action["contribution"]["predicted_ms_saved"] == pytest.approx(18.0)
    assert action["contribution"]["estimator"] == "postgres_cost_calibrated"


def test_identical_configs_are_never_recosted(searcher):
    searcher.run(CANDS)
    searcher.cost([CANDS[0]])
    assert len(searcher.calls) == len(set(searcher.calls))
    assert searcher.trace.cache_hits >= 1


def test_storage_penalty_can_reject_an_index(searcher):
    # A 0.01 drop in time cannot pay for 1 MB against a 25 MB budget at lambda 0.25 plus the
    # write penalty, so the C index alone is never chosen.
    config = searcher.run([CANDS[2]])
    assert config["actions"] == []


def test_live_search_recommends_q1_index():
    """Component: real miner, real HypoPG, calibrated predictor; translate via dehash."""
    config, trace = search.run()
    assert errors("Config", config) == []
    assert config["actions"], "search recommended nothing"
    first = config["actions"][0]
    text = " ".join([first["table"]] + first["columns"])
    names = httpx.post(os.environ["GATEWAY_URL"] + "/v1/answers/dehash",
                       json={"question_id": "qn_00000000", "text": text, "numbers": []}, timeout=30).json()["text"]
    assert names == "sales region_id transaction_date"
    assert trace.final_ms < trace.baseline_ms
    assert len(config["actions"]) <= cfg("rl.actions_per_episode")
