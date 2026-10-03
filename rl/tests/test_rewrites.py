"""Rewrite actions and the top-3 twin re-check, with a fake gateway (no database): rewrites are
offered only for matching, non-rejected pairs; Q-learning finds rewrite + index when only the
pair pays; the re-check picks the best measured configuration and penalises estimator/HypoPG
disagreement; the same actions are measured on the twin once."""
import httpx
import pytest

from contracts.validate import errors
from models.gnn.predictor import CostPredictor
from rl import search

T, Q = "t_aaaaaaaa", "q_00000001"
RULE = "date_trunc_eq_to_range"


def cand(n, col):
    return {"cand_id": f"cand_0000000{n}", "table": T, "columns": [col], "support": 1.0,
            "evidence": {"items": [f"{col}:EQ"], "templates": [Q]}}


X, Y, Z = cand(1, "c_00000001"), cand(2, "c_00000002"), cand(3, "c_00000003")
RW = {"cand_id": f"rw:{Q}:{RULE}", "template_id": Q, "rule_id": RULE}


def keys(actions):
    return frozenset("rw" if a["type"] == "rewrite" else a["columns"][0] for a in actions)


def fake_post(cost, measured=None, calls=None):
    """cost / measured: {frozenset of index columns and "rw": value}; unknown sets take the best
    known subset. measured is the twin's after_ms against a before of 1000."""
    def best(table, key):
        return min(v for k, v in table.items() if k <= key)

    def post(path, body):
        (calls if calls is not None else []).append(path)
        key = keys(body["actions"])
        n_idx = sum(a["type"] == "add_index" for a in body["actions"])
        if path == "/v1/simulate/hypopg":
            plan = {"plan_id": "p_00000009", "template_id": Q, "setup_id": "s_x", "source": "hypopg",
                    "nodes": [{"node_id": 0, "parent_id": None, "op": "Seq Scan", "est_rows": 1, "est_cost": best(cost, key), "width": 8}]}
            return {"plans": [plan], "index_storage_mb": float(n_idx)}
        assert path == "/v1/simulate/twin"
        return {"config_id": body["config_id"], "source": "twin", "write_ms_delta": None, "storage_mb_delta": float(n_idx),
                "runs": 5, "templates": [{"template_id": Q, "before_ms": 1000.0, "after_ms": best(measured, key)}]}
    return post


def make(monkeypatch, post, model=None):
    monkeypatch.setattr(search.gw, "post", post)
    monkeypatch.setattr(search, "_TWIN", {})
    if model is None:
        model = CostPredictor()
        model.ms_per_cost = 0.02
    tpl = [{"template_id": Q, "calls": 1, "total_ms": 1.0, "columns": []}]
    return search.QLearningSearch(tpl, [], [{"table": T, "size_mb": 100.0}], model, None, q={})


def test_rewrites_offered_only_for_matching_pairs_not_rejected(monkeypatch):
    # The gateway's candidate list holds only shape-matching pairs; of those, a Rejected pair
    # and one whose values do not fit (409) are not offered.
    status = {"q_00000001": "TestedOnly", "q_00000002": "Rejected"}

    def post(path, body):
        assert path == "/v1/rewrite/verify"
        if body["template_id"] == "q_00000003":
            raise httpx.HTTPStatusError("no", request=httpx.Request("POST", "http://gw"), response=httpx.Response(409))
        return {"status": status[body["template_id"]], "checks": {"verieql": "unsupported", "checksum": "match"}}
    monkeypatch.setattr(search.gw, "post", post)
    matching = [{"template_id": t, "rule_id": RULE} for t in ("q_00000001", "q_00000002", "q_00000003")]
    options, checks = search.rewrite_options(matching)
    assert [(o["template_id"], o["rule_id"]) for o in options] == [("q_00000001", RULE)]
    assert [c["status"] for c in checks] == ["TestedOnly", "Rejected", "NotApplicable"]
    assert search.rewrite_options([]) == ([], [])


def test_qlearning_finds_rewrite_plus_index_when_only_the_pair_pays(monkeypatch):
    # Rewrite alone costs slightly more, the index alone saves too little to pay its penalties,
    # together they cut the cost by 90%. Greedy needs each step to pay, so it stops at nothing.
    cost = {frozenset(): 1000, frozenset({"rw"}): 1010, frozenset({X["columns"][0]}): 990,
            frozenset({"rw", X["columns"][0]}): 100}
    rl = make(monkeypatch, fake_post(cost))
    config = rl.run([X, RW])
    assert errors("Config", config) == []
    assert sorted(a["type"] for a in config["actions"]) == ["add_index", "rewrite"]
    rewrite = next(a for a in config["actions"] if a["type"] == "rewrite")
    assert rewrite == {"type": "rewrite", "template_id": Q, "rule_id": RULE, "contribution": rewrite["contribution"]}
    greedy = search.GreedySearch(rl.templates, [], [{"table": T, "size_mb": 100.0}], rl.model)
    assert greedy.run([X, RW])["actions"] == []


def test_recheck_picks_the_best_measured_not_the_best_predicted(monkeypatch):
    c1, c2, c3 = X["columns"][0], Y["columns"][0], Z["columns"][0]
    predicted = {frozenset(): 1000, frozenset({c1}): 300, frozenset({c2}): 400, frozenset({c3}): 500}
    measured = {frozenset(): 1000, frozenset({c1}): 600, frozenset({c2}): 200, frozenset({c3}): 900}
    calls = []
    rl = make(monkeypatch, fake_post(predicted, measured, calls))
    assert [a["cand_id"] for a in rl.run([X, Y, Z])["actions"]] == [X["cand_id"]]    # best predicted
    config = rl.recheck()
    assert errors("Config", config) == []
    assert [a["cand_id"] for a in config["actions"]] == [Y["cand_id"]]               # best measured
    entries = rl.trace.top_configs
    assert len(entries) == 3 and all("measured_drop" in e and e["twin"]["templates"] for e in entries)
    chosen = [e for e in entries if e["chosen"]]
    assert len(chosen) == 1 and chosen[0]["score"] == max(e["score"] for e in entries)
    assert chosen[0]["measured_drop"] == pytest.approx(0.8)
    assert rl.trace.final_choice == "best measured on the twin"
    assert calls.count("/v1/simulate/twin") == 3


class SkewedModel(CostPredictor):
    """An estimator that believes the 510-cost plan is ten times faster than its cost says."""
    def predict(self, plan):
        out = super().predict(plan)
        return {**out, "total_ms": {510: 2.0}.get(plan["nodes"][0]["est_cost"], out["total_ms"])}


def test_recheck_penalises_estimator_hypopg_disagreement(monkeypatch):
    # X: estimator says a 90% drop, raw HypoPG cost only 49%. Y: both say 50%. The twin measures
    # them equal, so the disagreement penalty decides for Y.
    c1, c2 = X["columns"][0], Y["columns"][0]
    model = SkewedModel()
    model.ms_per_cost = 0.02
    rl = make(monkeypatch, fake_post({frozenset(): 1000, frozenset({c1}): 510, frozenset({c2}): 500},
                                     {frozenset(): 1000, frozenset({c1}): 300, frozenset({c2}): 300}), model)
    assert [a["cand_id"] for a in rl.run([X, Y])["actions"]] == [X["cand_id"]]
    config = rl.recheck()
    assert [a["cand_id"] for a in config["actions"]] == [Y["cand_id"]]
    by_id = {tuple(e["cand_ids"]): e for e in rl.trace.top_configs}
    assert by_id[(X["cand_id"],)]["disagreement"] == pytest.approx(0.41)
    assert by_id[(Y["cand_id"],)]["disagreement"] == pytest.approx(0.0)
    assert by_id[(X["cand_id"],)]["measured_reward"] == by_id[(Y["cand_id"],)]["measured_reward"]


def test_same_actions_are_measured_on_the_twin_once(monkeypatch):
    calls = []
    make(monkeypatch, fake_post({frozenset(): 1}, {frozenset(): 1000, frozenset({"rw"}): 100}, calls))
    a = {"type": "rewrite", "template_id": Q, "rule_id": RULE}
    first, cached1 = search.twin({"config_id": "cfg_00000001", "search": "q_learning", "actions": [a]})
    second, cached2 = search.twin({"config_id": "cfg_00000002", "search": "q_learning", "actions": [a]})
    assert (cached1, cached2) == (False, True) and calls == ["/v1/simulate/twin"]
    assert second["config_id"] == "cfg_00000002" and second["templates"] == first["templates"]
