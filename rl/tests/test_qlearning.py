"""Q-learning tests with a fake gateway of known costs (no database). Covers the doc's RL
acceptance checks that can be shown without live data: it matches greedy on the simple case,
beats greedy when indexes overlap, and adapts to new template weights without restarting."""
import pytest

from contracts.validate import errors
from models.gnn.predictor import CostPredictor
from rl import search

T = "t_aaaaaaaa"


def cand(n, col):
    return {"cand_id": f"cand_0000000{n}", "table": T, "columns": [col], "support": 1.0,
            "evidence": {"items": [f"{col}:EQ"], "templates": ["q_00000001"]}}


X, Y, Z = cand(1, "c_00000001"), cand(2, "c_00000002"), cand(3, "c_00000003")


def fake_post(costs):
    """costs: {template_id: {frozenset of columns: root est_cost}}; unknown sets cost as the best
    known subset (an extra index never hurts the read)."""
    def post(path, body):
        key = frozenset(a["columns"][0] for a in body["actions"])
        plans = []
        for tid, table in costs.items():
            cost = min(v for k, v in table.items() if k <= key)
            plans.append({"plan_id": "p_00000009", "template_id": tid, "setup_id": "s_x", "source": "hypopg",
                          "nodes": [{"node_id": 0, "parent_id": None, "op": "Seq Scan", "est_rows": 1, "est_cost": cost, "width": 8}]})
        return {"plans": plans, "index_storage_mb": float(len(key))}
    return post


def make(monkeypatch, costs, cls, weights=None, q=None):
    monkeypatch.setattr(search.gw, "post", fake_post(costs))
    model = CostPredictor()
    model.ms_per_cost = 0.02
    tpl = [{"template_id": t, "calls": 1, "total_ms": 1.0, "columns": []} for t in costs]
    kw = {"q": {} if q is None else q} if cls is search.QLearningSearch else {}
    return cls(tpl, [], [{"table": T, "size_mb": 100.0}], model, weights, **kw)


# Overlap: X is the best single index, but Y and Z together beat anything with X.
c1, c2, c3 = "c_00000001", "c_00000002", "c_00000003"
OVERLAP = {"q_00000001": {frozenset(): 1000, frozenset({c1}): 500, frozenset({c2}): 600, frozenset({c3}): 600,
                          frozenset({c1, c2}): 480, frozenset({c1, c3}): 480, frozenset({c2, c3}): 100}}


def picked(config):
    return sorted(a["cand_id"] for a in config["actions"])


def test_matches_greedy_without_overlap(monkeypatch):
    simple = {"q_00000001": {frozenset(): 1000, frozenset({c1}): 100, frozenset({c2}): 990, frozenset({c3}): 990}}
    rl = make(monkeypatch, simple, search.QLearningSearch).run([X, Y, Z])
    gr = make(monkeypatch, simple, search.GreedySearch).run([X, Y, Z])
    assert errors("Config", rl) == [] and rl["search"] == "q_learning"
    assert picked(rl) == picked(gr) == [X["cand_id"]]


def test_beats_greedy_when_indexes_overlap(monkeypatch):
    gr = make(monkeypatch, OVERLAP, search.GreedySearch)
    assert picked(gr.run([X, Y, Z])) == [X["cand_id"]]
    rl = make(monkeypatch, OVERLAP, search.QLearningSearch)
    assert picked(rl.run([X, Y, Z])) == sorted([Y["cand_id"], Z["cand_id"]])
    assert rl.trace.final_ms < gr.trace.final_ms
    assert rl.trace.top_configs and rl.trace.episodes > 0


def test_adapts_to_new_weights_without_restarting(monkeypatch):
    drift = {"q_00000001": {frozenset(): 1000, frozenset({c1}): 100},
             "q_00000002": {frozenset(): 1000, frozenset({c2}): 100}}
    q = {}
    first = make(monkeypatch, drift, search.QLearningSearch, {"q_00000001": 1.0, "q_00000002": 0.0}, q).run([X, Y])
    assert picked(first) == [X["cand_id"]]
    learned = len(q)
    second = make(monkeypatch, drift, search.QLearningSearch, {"q_00000001": 0.0, "q_00000002": 1.0}, q).run([X, Y])
    assert picked(second) == [Y["cand_id"]]
    assert len(q) >= learned   # same table, kept and extended, not reset


def test_stop_when_nothing_pays(monkeypatch):
    flat = {"q_00000001": {frozenset(): 1000, frozenset({c1}): 999}}
    assert make(monkeypatch, flat, search.QLearningSearch).run([X])["actions"] == []
