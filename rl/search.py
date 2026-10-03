"""Configuration search: run() -> Config.

SIMPLIFIED for the walking skeleton: greedy search, not Q-learning. Label: LABEL below.
This is the doc's "greedy baseline" (Detailed component specs, RL agent): keep adding the
single best action until nothing improves.

Scoring per configuration, all from hashed data:
- workload time W(config) = sum over slow templates of weight x predicted total ms of the
  template's HypoPG plan under that configuration (weights = share of calls);
- reward of adding one index = (W(before) - W(after)) / W(baseline)
                               - lambda_write x write_penalty_ms_per_index
                               - lambda_storage x added MB / (storage budget share x table MB).
The write penalty is an assumption from config.yaml, not a measurement (the doc allows a
per-index penalty during search); the final choice is measured on the twin.
Identical configurations are never re-costed (cache keyed by the set of candidate IDs).

TODO(RL): replace the greedy loop with tabular Q-learning (rl.alpha, rl.gamma, rl.epsilon_*,
rl.episodes from config.yaml) behind the same run() -> Config interface; Config.search
becomes "q_learning".
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent import gateway_client as gw
from common.config import cfg
from miner import fpgrowth
from models.gnn import predictor as pred

LABEL = "search: greedy (RL pending)"


def _config(actions: list[dict]) -> dict:
    key = "|".join(f"{a['table']}:{','.join(a['columns'])}" for a in actions)
    return {"config_id": "cfg_" + hashlib.sha256(key.encode()).hexdigest()[:8], "search": "greedy", "actions": actions}


@dataclass
class Trace:
    """Everything the search measured or predicted, for the dashboard and the LLM."""
    baseline_ms: float = 0.0
    final_ms: float = 0.0
    steps: list[dict] = field(default_factory=list)
    evaluated: int = 0
    cache_hits: int = 0


class GreedySearch:
    def __init__(self, templates: list[dict], column_meta: list[dict], table_meta: list[dict],
                 model: pred.CostPredictor, weights: dict[str, float] | None = None):
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

    def run(self, candidates: list[dict]) -> dict:
        lam_w, lam_s = float(cfg("rl.lambda_write")), float(cfg("rl.lambda_storage"))
        write_penalty = float(cfg("rl.write_penalty_ms_per_index"))
        budget_share = float(cfg("rl.storage_budget_table_share"))
        max_actions = int(cfg("rl.actions_per_episode"))

        chosen: list[dict] = []
        base_ms, base_mb = self.cost(chosen)
        self.trace.baseline_ms = base_ms
        cur_ms, cur_mb = base_ms, base_mb
        actions: list[dict] = []
        while len(chosen) < max_actions:
            best = None
            for c in candidates:
                if c in chosen:
                    continue
                ms, mb = self.cost(chosen + [c])
                budget_mb = budget_share * self.table_mb.get(c["table"], 0.0)
                storage_term = lam_s * (mb - cur_mb) / budget_mb if budget_mb > 0 else float("inf")
                reward = (cur_ms - ms) / base_ms - lam_w * write_penalty - storage_term
                if best is None or reward > best[0]:
                    best = (reward, c, ms, mb)
            if best is None or best[0] <= 0:
                break
            reward, c, ms, mb = best
            chosen.append(c)
            actions.append({"type": "add_index", "table": c["table"], "columns": c["columns"], "cand_id": c["cand_id"],
                            "contribution": {"predicted_ms_saved": round(cur_ms - ms, 3), "estimator": pred.ESTIMATOR}})
            self.trace.steps.append({"cand_id": c["cand_id"], "reward": round(reward, 4),
                                     "predicted_ms_before": round(cur_ms, 3), "predicted_ms_after": round(ms, 3),
                                     "index_storage_mb": round(mb - cur_mb, 3)})
            cur_ms, cur_mb = ms, mb
        self.trace.final_ms = cur_ms
        return _config(actions)


def run(weights: dict[str, float] | None = None) -> tuple[dict, Trace]:
    """Fetch hashed inputs from the gateway, mine candidates, calibrate the predictor on the
    measured plans, and search. Returns (Config, Trace)."""
    templates = gw.get("/v1/templates/slow")
    column_meta = gw.get("/v1/meta/columns")
    table_meta = gw.get("/v1/meta/tables")
    existing = [(c["table"], [c["col"]]) for c in column_meta if c["bits"]["pk"]]
    candidates = fpgrowth.candidates(templates, column_meta, existing)
    measured = [p for t in templates for p in gw.get(f"/v1/templates/{t['template_id']}/plans")]
    model = pred.CostPredictor().fit(measured)
    search = GreedySearch(templates, column_meta, table_meta, model, weights)
    return search.run(candidates), search.trace
