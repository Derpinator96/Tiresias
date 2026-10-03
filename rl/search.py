"""Configuration search: run() -> Config.

QLearningSearch (doc, Component 4 and Detailed component specs, RL agent): tabular
Q-learning with epsilon-greedy exploration. State = the set of candidates chosen so far;
actions = add one remaining candidate, or stop; an episode ends after rl.actions_per_episode
actions or a stop. The Q-table persists across run() calls in this process, so new template
weights (drift) continue learning instead of restarting. Unseen (state, action) pairs start
at rl.q_init (optimistic), so every option is tried before the agent settles; with Q at 0,
ties went to list order and a strong first index starved the better pair behind it
(rl/tests/test_qlearning.py::test_beats_greedy_when_indexes_overlap). The final Config is
the visited configuration with the highest total reward, in the order it was built (doc:
"re-score the top configurations" rather than trust Q-values that may be under-learned).
GreedySearch is the doc's greedy baseline: keep adding the single best action until nothing
improves. Both share one cost cache and one reward, and run() reports both.

SIMPLIFIED, label LABEL below: index actions only (rewrite and partition actions MISSING),
and the doc's final re-check of the top 3 configurations on the twin is MISSING (the top 3
are listed in the trace; the chosen one is measured on the twin by /v1/simulate/twin).

Scoring per configuration, all from hashed data:
- workload time W(config) = sum over slow templates of weight x predicted total ms of the
  template's HypoPG plan under that configuration (weights = share of calls);
- reward of adding one index = (W(before) - W(after)) / W(baseline)
                               - lambda_write x write_penalty_ms_per_index
                               - lambda_storage x added MB / (storage budget share x table MB).
The write penalty is an assumption from config.yaml, not a measurement (the doc allows a
per-index penalty during search); the final choice is measured on the twin.
Identical configurations are never re-costed (cache keyed by the set of candidate IDs).

"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from agent import gateway_client as gw
from common.config import cfg
from miner import fpgrowth
from models.gnn import predictor as pred

LABEL = "search: Q-learning, index actions only (rewrite, partition and top-3 twin re-check pending)"
STOP = "stop"
_Q: dict[tuple[frozenset, str], float] = {}   # persists across run() calls (drift keeps learning)


def _config(actions: list[dict], search: str = "greedy") -> dict:
    key = "|".join(f"{a['table']}:{','.join(a['columns'])}" for a in actions)
    return {"config_id": "cfg_" + hashlib.sha256(key.encode()).hexdigest()[:8], "search": search, "actions": actions}


@dataclass
class Trace:
    """Everything the search measured or predicted, for the dashboard and the LLM."""
    baseline_ms: float = 0.0
    final_ms: float = 0.0
    steps: list[dict] = field(default_factory=list)
    evaluated: int = 0
    cache_hits: int = 0
    episodes: int = 0
    top_configs: list[dict] = field(default_factory=list)
    greedy: dict = field(default_factory=dict)


class GreedySearch:
    def __init__(self, templates: list[dict], column_meta: list[dict], table_meta: list[dict],
                 model, weights: dict[str, float] | None = None):
        self.templates = templates
        calls = {t["template_id"]: t["calls"] for t in templates}
        total = sum(calls.values()) or 1
        self.weights = weights or {tid: c / total for tid, c in calls.items()}
        self.table_mb = {t["table"]: t["size_mb"] for t in table_meta}
        self.meta = column_meta
        self.model = model
        self._cache: dict[frozenset, tuple[float, float]] = {}
        self.trace = Trace()

    def cost(self, chosen: list[dict]) -> tuple[float, float]:
        """(workload ms, hypothetical index MB) for a set of chosen candidates."""
        key = frozenset(c["cand_id"] for c in chosen)
        if key in self._cache:
            self.trace.cache_hits += 1
            return self._cache[key]
        cfg_obj = _config([{"type": "add_index", "table": c["table"], "columns": c["columns"]} for c in chosen])
        out = gw.post("/v1/simulate/hypopg", cfg_obj)
        w = sum(self.weights.get(p["template_id"], 0.0) * pred.predict(p, self.model)["total_ms"] for p in out["plans"])
        self._cache[key] = (w, float(out["index_storage_mb"]))
        self.trace.evaluated += 1
        return self._cache[key]

    def reward(self, chosen: list[dict], c: dict, cur: tuple[float, float], base_ms: float) -> tuple[float, float, float]:
        """(reward, ms, MB) of adding candidate c to `chosen`, whose cost is `cur` (doc's reward)."""
        ms, mb = self.cost(chosen + [c])
        budget_mb = float(cfg("rl.storage_budget_table_share")) * self.table_mb.get(c["table"], 0.0)
        storage_term = float(cfg("rl.lambda_storage")) * (mb - cur[1]) / budget_mb if budget_mb > 0 else float("inf")
        write_term = float(cfg("rl.lambda_write")) * float(cfg("rl.write_penalty_ms_per_index"))
        return (cur[0] - ms) / base_ms - write_term - storage_term, ms, mb

    def _apply(self, chosen, actions, c, reward, cur, ms, mb):
        chosen.append(c)
        actions.append({"type": "add_index", "table": c["table"], "columns": c["columns"], "cand_id": c["cand_id"],
                        "contribution": {"predicted_ms_saved": round(cur[0] - ms, 3), "estimator": self.model.estimator}})
        self.trace.steps.append({"cand_id": c["cand_id"], "reward": round(reward, 4),
                                 "predicted_ms_before": round(cur[0], 3), "predicted_ms_after": round(ms, 3),
                                 "index_storage_mb": round(mb - cur[1], 3)})

    def run(self, candidates: list[dict]) -> dict:
        max_actions = int(cfg("rl.actions_per_episode"))
        chosen: list[dict] = []
        cur = self.cost(chosen)
        base_ms = self.trace.baseline_ms = cur[0]
        actions: list[dict] = []
        while len(chosen) < max_actions:
            scored = [(self.reward(chosen, c, cur, base_ms), c) for c in candidates if c not in chosen]
            if not scored:
                break
            (reward, ms, mb), c = max(scored, key=lambda x: x[0][0])
            if reward <= 0:
                break
            self._apply(chosen, actions, c, reward, cur, ms, mb)
            cur = (ms, mb)
        self.trace.final_ms = cur[0]
        return _config(actions)


class QLearningSearch(GreedySearch):
    def __init__(self, *args, q: dict | None = None, seed: int | None = None, **kw):
        super().__init__(*args, **kw)
        self.q = _Q if q is None else q
        self.rng = random.Random(int(cfg("dataset.random_seed")) if seed is None else seed)

    def _q(self, state: frozenset, option) -> float:
        return self.q.get((state, self._key(option)), float(cfg("rl.q_init")))

    def _best(self, state: frozenset, options: list) -> tuple[object, float]:
        """Highest-Q option; ties keep list order (candidates as mined, then stop)."""
        return max(((o, self._q(state, o)) for o in options), key=lambda x: x[1])

    @staticmethod
    def _key(option) -> str:
        return STOP if option == STOP else option["cand_id"]

    def run(self, candidates: list[dict]) -> dict:
        alpha, gamma = float(cfg("rl.alpha")), float(cfg("rl.gamma"))
        eps0, eps1 = float(cfg("rl.epsilon_start")), float(cfg("rl.epsilon_min"))
        episodes, max_actions = int(cfg("rl.episodes")), int(cfg("rl.actions_per_episode"))
        base = self.cost([])
        base_ms = self.trace.baseline_ms = base[0]
        returns: dict[frozenset, tuple[float, float, list[dict]]] = {frozenset(): (0.0, base[0], [])}
        for ep in range(episodes):
            eps = eps0 + (eps1 - eps0) * ep / max(1, episodes - 1)   # linear decay
            chosen, state, cur, ret = [], frozenset(), base, 0.0
            for step in range(max_actions):
                options = [c for c in candidates if c not in chosen] + [STOP]
                a = self.rng.choice(options) if self.rng.random() < eps else self._best(state, options)[0]
                k = (state, self._key(a))
                if a == STOP:
                    self.q[k] = self._q(state, a) + alpha * (0.0 - self._q(state, a))
                    break
                r, ms, mb = self.reward(chosen, a, cur, base_ms)
                nxt = state | {a["cand_id"]}
                rest = [c for c in candidates if c not in chosen and c is not a] + [STOP]
                future = self._best(nxt, rest)[1] if step + 1 < max_actions else 0.0
                self.q[k] = self._q(state, a) + alpha * (r + gamma * future - self._q(state, a))
                chosen, state, cur, ret = chosen + [a], nxt, (ms, mb), ret + r
                if state not in returns or ret > returns[state][0]:
                    returns[state] = (ret, ms, list(chosen))
        self.trace.episodes = episodes
        ranked = sorted(returns.items(), key=lambda x: (-x[1][0], len(x[0])))
        self.trace.top_configs = [{"cand_ids": sorted(st), "return": round(r, 4), "predicted_ms": round(ms, 3)}
                                  for st, (r, ms, _) in ranked[:int(cfg("rl.configs_verified_on_twin"))]]
        # Final config: the best visited configuration, rebuilt in the order it was found so
        # each action's contribution is its own predicted saving. An empty config wins ties.
        chosen, actions, cur = [], [], base
        for a in ranked[0][1][2]:
            r, ms, mb = self.reward(chosen, a, cur, base_ms)
            self._apply(chosen, actions, a, r, cur, ms, mb)
            cur = (ms, mb)
        self.trace.final_ms = cur[0]
        return _config(actions, "q_learning")


def run(weights: dict[str, float] | None = None) -> tuple[dict, Trace]:
    """Fetch hashed inputs from the gateway, mine candidates, calibrate the predictor on the
    measured plans, and search. Returns (Config, Trace)."""
    templates = gw.get("/v1/templates/slow")
    column_meta = gw.get("/v1/meta/columns")
    table_meta = gw.get("/v1/meta/tables")
    existing = [(c["table"], [c["col"]]) for c in column_meta if c["bits"]["pk"]]
    candidates = fpgrowth.candidates(templates, column_meta, existing)
    measured = [p for t in templates for p in gw.get(f"/v1/templates/{t['template_id']}/plans")]
    model = pred.load_predictor().fit(measured)
    rl = QLearningSearch(templates, column_meta, table_meta, model, weights)
    config = rl.run(candidates)
    # The doc's comparison: greedy on the same cost cache, reported next to the RL result.
    greedy = GreedySearch(templates, column_meta, table_meta, model, weights)
    greedy._cache = rl._cache
    g = greedy.run(candidates)
    rl.trace.greedy = {"config_id": g["config_id"], "cand_ids": [a["cand_id"] for a in g["actions"]],
                       "predicted_ms": round(greedy.trace.final_ms, 3), "same_as_rl": g["config_id"] == config["config_id"]}
    return config, rl.trace
