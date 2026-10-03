"""Configuration search: run() -> Config.

QLearningSearch (doc, Component 4 and Detailed component specs, RL agent): tabular
Q-learning with epsilon-greedy exploration. State = the set of candidates chosen so far;
actions = add one remaining candidate, or stop; an episode ends after rl.actions_per_episode
actions or a stop. The Q-table persists across run() calls in this process, so new template
weights (drift) continue learning instead of restarting. Unseen (state, action) pairs start
at rl.q_init (optimistic), so every option is tried before the agent settles; with Q at 0,
ties went to list order and a strong first index starved the better pair behind it
(rl/tests/test_qlearning.py::test_beats_greedy_when_indexes_overlap). run() returns the
visited configuration with the highest total reward (rather than trust Q-values that may be
under-learned); recheck() then picks among the top ones by twin measurement (below). A Config
lists its actions largest predicted saving first.
GreedySearch is the doc's greedy baseline: keep adding the single best action until nothing
improves. Both share one cost cache and one reward, and run() reports both.

Actions: add one mined index candidate, or apply one rewrite rule to one template. Rewrites are
offered only for the (template, rule) pairs the gateway matched by shape (doc: only matching
rules), and only once the gateway's check (VeriEQL plus a twin checksum) has not rejected them.
A rewrite builds nothing, so it carries no write or storage penalty. The miner also mines the
rewritten shapes (miner.fpgrowth.with_rewritten_shapes), so an index that only helps after a
rewrite is a candidate too.

Final choice (doc, Detailed component specs): the top rl.configs_verified_on_twin visited
configurations are re-scored with raw HypoPG cost next to the estimator, measured on the twin,
and the best measured score wins: measured fractional drop in workload time, minus the same
write and storage penalties (storage as measured on the twin), minus rl.lambda_disagreement x
|estimator's predicted drop - raw HypoPG cost drop|. With the calibrated Postgres baseline the
estimator is HypoPG cost times one ratio, so the disagreement is zero by construction; it bites
once the GNN serves.

Partition (doc, Component 4 item 6: "scored on the twin only, for at most two candidate keys,
after the index search"; HypoPG cannot hypothesise a partition): after the re-check, up to
rl.partition_max_keys monthly range keys (partition_keys: a date column a slow template filters
on, largest table first) are each added to the chosen configuration and measured on the twin
(the gateway builds a partitioned copy there). A key is kept only if its measured score, the
same formula with storage as measured (the partitioned copy minus the table, plus the indexes),
beats the chosen configuration's; at most one is kept. A partition builds no new index, so the
assumed per-index write penalty does not grow; the twin's measured write_ms_delta is reported
next to it. The estimator's predicted numbers never include the partition. Greedy does not
search partitions, so the greedy comparison is made before this step.

SIMPLIFIED, label LABEL below: drop-index actions MISSING. During the search, write cost is an
assumed per-index penalty (the doc allows it); pgbench measures write cost on the twin
(db/sandbox/write_cost.py) and the measured numbers are reported, not scored.

Scoring per configuration, all from hashed data:
- workload time W(config) = sum over slow templates of weight x predicted total ms of the
  template's HypoPG plan under that configuration (weights = share of calls);
- reward of adding one index = (W(before) - W(after)) / W(baseline)
                               - lambda_write x write_penalty_ms_per_index
                               - lambda_storage x added MB / (storage budget share x table MB).
The write penalty is an assumption from config.yaml, not a measurement (the doc allows a
per-index penalty during search); the final choice is measured on the twin.
Identical configurations are never re-costed (cache keyed by the set of candidate IDs); run()
also reuses HypoPG and twin results for the same set of actions across calls in this process
for rl.sim_cache_s, so the LLM's run_rl right after /ai/rl/run costs and measures nothing new.

"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field

import httpx

from agent import gateway_client as gw
from common.config import cfg
from miner import fpgrowth
from models.gnn import predictor as pred

LABEL = (f"search: Q-learning over index and rewrite actions, top {cfg('rl.configs_verified_on_twin')} "
         f"re-checked on the twin; then up to {cfg('rl.partition_max_keys')} monthly partition keys measured on the "
         "twin only (drop-index actions pending)")
PARTITION_LABEL = ("partition: monthly range keys measured on the twin only (HypoPG cannot simulate them), "
                   "tried after the index and rewrite search; predictions do not include them")
STOP = "stop"
_Q: dict[tuple[frozenset, str], float] = {}   # persists across run() calls (drift keeps learning)
# Gateway results per set of actions: (monotonic time, response). Shared by every search in
# this process; reused for rl.sim_cache_s (doc: identical configs are never re-costed).
_HYPO: dict[tuple, tuple[float, dict]] = {}
_TWIN: dict[tuple, tuple[float, dict]] = {}
# The slow templates of the latest run(). Part of every cache key: a result measured before the
# workload changed (drift adds Q4) covers other templates and must not be reused.
_WORKLOAD: frozenset = frozenset()


def _akey(a: dict) -> str:
    if a["type"] == "partition":
        return f"part:{a['table']}:{a['column']}"
    return f"{a['template_id']}:{a['rule_id']}" if a["type"] == "rewrite" else f"{a['table']}:{','.join(a['columns'])}"


def _config(actions: list[dict], search: str = "greedy") -> dict:
    key = "|".join(_akey(a) for a in actions)
    return {"config_id": "cfg_" + hashlib.sha256(key.encode()).hexdigest()[:8], "search": search, "actions": actions}


def _is_rewrite(option: dict) -> bool:
    return "rule_id" in option


def _action(option: dict) -> dict:
    """Config action for a search option: a mined index candidate or a matching rewrite."""
    if _is_rewrite(option):
        return {"type": "rewrite", "template_id": option["template_id"], "rule_id": option["rule_id"]}
    return {"type": "add_index", "table": option["table"], "columns": option["columns"]}


def _simulate(path: str, config: dict, store: dict) -> tuple[dict, bool]:
    """(gateway response, from cache) for `config`, reused for rl.sim_cache_s per set of actions.
    ponytail: time-based cache; a twin or pg-prod reseeded within the TTL serves stale numbers
    until it expires. Key it on a data version if the gateway ever exposes one."""
    key = (frozenset(_akey(a) for a in config["actions"]), _WORKLOAD)
    hit = store.get(key)
    if hit and time.monotonic() - hit[0] < float(cfg("rl.sim_cache_s")):
        return hit[1], True
    if any(a["type"] == "partition" for a in config["actions"]):   # builds a table copy on the twin
        out = gw.post(path, config, timeout=float(cfg("rl.partition_twin_timeout_s")))
    else:
        out = gw.post(path, config)
    store[key] = (time.monotonic(), out)
    return out, False


def twin(config: dict) -> tuple[dict, bool]:
    """(SimResult, from cache) for `config` measured on the twin. The LLM's run_rl and simulate
    reuse what /ai/rl/run just measured instead of rebuilding the same indexes."""
    sim, cached = _simulate("/v1/simulate/twin", config, _TWIN)
    return {**sim, "config_id": config["config_id"]}, cached


def rewrite_options(rewrites: list[dict]) -> tuple[list[dict], list[dict]]:
    """(search options, check per pair) for the gateway's rewrite candidates, which hold only
    the (template, rule) pairs whose shape matches. A pair is offered once /v1/rewrite/verify
    says Verified or TestedOnly; Rejected, or a rule the logged values do not allow (409), is
    never offered."""
    options, checks = [], []
    for r in rewrites:
        tid, rule = r["template_id"], r["rule_id"]
        try:
            rw = gw.post("/v1/rewrite/verify", {"template_id": tid, "rule_id": rule})
            status, detail = rw["status"], rw["checks"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 409:
                raise
            status, detail = "NotApplicable", {}
        checks.append({"template_id": tid, "rule_id": rule, "status": status, "checks": detail})
        if status in ("Verified", "TestedOnly"):
            options.append({"cand_id": f"rw:{tid}:{rule}", "template_id": tid, "rule_id": rule})
    return options, checks


def partition_keys(templates: list[dict], column_meta: list[dict], table_meta: list[dict]) -> list[dict]:
    """Partition actions to try: date columns a slow template filters on (EQ or RANGE), largest
    table first, then most template time; at most rl.partition_max_keys."""
    dates = {c["col"]: c["table"] for c in column_meta if c["type_class"] == "date"}
    size = {t["table"]: t["size_mb"] for t in table_meta}
    used: dict[str, float] = {}
    for t in templates:
        for col in {c["col"] for c in t["columns"] if c["role"] in ("EQ", "RANGE") and c["col"] in dates}:
            used[col] = used.get(col, 0.0) + float(t["total_ms"])
    ranked = sorted(used, key=lambda col: (-size.get(dates[col], 0.0), -used[col], col))
    return [{"type": "partition", "table": dates[col], "column": col, "scheme": "range_month"}
            for col in ranked[:int(cfg("rl.partition_max_keys"))]]


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
    rewrites: list[dict] = field(default_factory=list)
    final_choice: str = "best predicted"
    partition: dict = field(default_factory=dict)


class GreedySearch:
    def __init__(self, templates: list[dict], column_meta: list[dict], table_meta: list[dict],
                 model, weights: dict[str, float] | None = None):
        self.templates = templates
        calls = {t["template_id"]: t["calls"] for t in templates}
        total = sum(calls.values()) or 1
        # Weights of templates that are no longer slow cannot steer the search; with none left
        # (a drift window of a template since reset), the workload time would be 0, so fall back
        # to call shares.
        weights = {tid: w for tid, w in (weights or {}).items() if tid in calls}
        self.weights = weights or {tid: c / total for tid, c in calls.items()}
        self.table_mb = {t["table"]: t["size_mb"] for t in table_meta}
        self.meta = column_meta
        self.model = model
        self._cache: dict[frozenset, tuple[float, float]] = {}
        self._raw: dict[frozenset, float] = {}   # weighted raw HypoPG root cost, for the re-check
        self._hypo: dict[tuple, tuple[float, dict]] = {}   # run() shares the module's _HYPO
        self.trace = Trace()

    def cost(self, chosen: list[dict]) -> tuple[float, float]:
        """(workload ms, hypothetical index MB) for a set of chosen options."""
        key = frozenset(c["cand_id"] for c in chosen)
        if key in self._cache:
            self.trace.cache_hits += 1
            return self._cache[key]
        out, _ = _simulate("/v1/simulate/hypopg", _config([_action(c) for c in chosen]), self._hypo)
        w = sum(self.weights.get(p["template_id"], 0.0) * pred.predict(p, self.model)["total_ms"] for p in out["plans"])
        self._raw[key] = sum(self.weights.get(p["template_id"], 0.0)
                             * next(n["est_cost"] for n in p["nodes"] if n["parent_id"] is None) for p in out["plans"])
        self._cache[key] = (w, float(out["index_storage_mb"]))
        self.trace.evaluated += 1
        return self._cache[key]

    def reward(self, chosen: list[dict], c: dict, cur: tuple[float, float], base_ms: float) -> tuple[float, float, float]:
        """(reward, ms, MB) of adding option c to `chosen`, whose cost is `cur` (doc's reward)."""
        ms, mb = self.cost(chosen + [c])
        if _is_rewrite(c):
            return (cur[0] - ms) / base_ms, ms, mb   # a rewrite builds nothing: no write or storage cost
        budget_mb = float(cfg("rl.storage_budget_table_share")) * self.table_mb.get(c["table"], 0.0)
        storage_term = float(cfg("rl.lambda_storage")) * (mb - cur[1]) / budget_mb if budget_mb > 0 else float("inf")
        write_term = float(cfg("rl.lambda_write")) * float(cfg("rl.write_penalty_ms_per_index"))
        return (cur[0] - ms) / base_ms - write_term - storage_term, ms, mb

    def _apply(self, chosen, actions, c, reward, cur, ms, mb):
        chosen.append(c)
        extra = {} if _is_rewrite(c) else {"cand_id": c["cand_id"]}
        actions.append({**_action(c), **extra,
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

    def _finish(self, opts: list[dict], search: str) -> dict:
        """Config for `opts`, largest predicted saving first; each action's contribution is its
        own saving given the actions listed before it."""
        base = self.cost([])
        self.trace.steps = []
        chosen, actions, cur, rest = [], [], base, list(opts)
        while rest:
            c = min(rest, key=lambda o: self.cost(chosen + [o])[0])
            r, ms, mb = self.reward(chosen, c, cur, base[0])
            self._apply(chosen, actions, c, r, cur, ms, mb)
            cur = (ms, mb)
            rest.remove(c)
        self.trace.final_ms = cur[0]
        return _config(actions, search)


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
        top = [(st, v) for st, v in ranked if st][:int(cfg("rl.configs_verified_on_twin"))]
        self.trace.top_configs = [{"cand_ids": sorted(st), "return": round(r, 4), "predicted_ms": round(ms, 3)}
                                  for st, (r, ms, _) in top]
        self.top = [opts for _, (_, _, opts) in top]
        # Before the twin re-check: the best visited configuration (an empty config wins ties).
        self.best_predicted = ranked[0][1][2]
        return self._finish(self.best_predicted, "q_learning")

    def _measured(self, sim: dict, cached: bool, n_indexes: int, tables: set[str], disagreement: float) -> dict:
        """Score of a twin measurement: measured drop in weighted workload time, minus the
        assumed per-index write penalty, minus measured storage against the budget of `tables`,
        minus lambda_disagreement x the estimator/HypoPG disagreement."""
        before = sum(self.weights.get(t["template_id"], 0.0) * t["before_ms"] for t in sim["templates"])
        after = sum(self.weights.get(t["template_id"], 0.0) * t["after_ms"] for t in sim["templates"])
        # ponytail: one storage budget for the whole config (share x the touched tables' size),
        # since the twin reports total MB, not per action.
        budget = float(cfg("rl.storage_budget_table_share")) * sum(self.table_mb.get(t, 0.0) for t in tables)
        storage = float(cfg("rl.lambda_storage")) * sim["storage_mb_delta"] / budget if budget > 0 else 0.0
        drop = 1 - after / before if before else 0.0
        reward = drop - float(cfg("rl.lambda_write")) * float(cfg("rl.write_penalty_ms_per_index")) * n_indexes - storage
        return {"twin": {"templates": sim["templates"], "storage_mb": sim["storage_mb_delta"], "runs": sim["runs"],
                         "cached": cached},
                "measured_drop": round(drop, 4), "measured_reward": round(reward, 4),
                "score": round(reward - float(cfg("rl.lambda_disagreement")) * disagreement, 4)}

    def add_partition(self, config: dict, keys: list[dict]) -> dict:
        """The doc's partition step, after recheck(): `config` plus each partition action in
        `keys`, measured on the twin; the best one is kept if its score beats the chosen
        configuration's (0 for no change). trace.partition records every measurement; a kept key
        turns the chosen top_configs entry into the measured config with the partition, its
        earlier numbers under without_partition."""
        chosen = next((e for e in self.trace.top_configs if e.get("chosen")), None)
        base = chosen["score"] if chosen else 0.0
        out = {"label": PARTITION_LABEL, "base_score": base, "keys": [], "kept": None}
        self.trace.partition = out
        if not keys:
            out["skipped"] = "no date column of a slow template to partition on"
            return config
        if self.trace.final_choice != "best measured on the twin":
            out["skipped"] = "the re-check measured nothing on the twin"
            return config
        if len(config["actions"]) >= int(cfg("rl.actions_per_episode")):
            out["skipped"] = "the configuration already holds the maximum number of actions"
            return config
        indexes = [a for a in config["actions"] if a["type"] == "add_index"]
        best = None
        for p in keys:
            trial = _config(config["actions"] + [p], config["search"])
            k = {"table": p["table"], "column": p["column"], "scheme": p["scheme"], "config_id": trial["config_id"]}
            try:
                sim, cached = twin(trial)
            except httpx.HTTPStatusError as err:
                out["keys"].append({**k, "twin_error": err.response.status_code})
                continue
            m = self._measured(sim, cached, len(indexes), {a["table"] for a in indexes} | {p["table"]},
                               chosen["disagreement"] if chosen else 0.0)
            k.update(m, write_ms_delta=sim["write_ms_delta"])
            out["keys"].append(k)
            if m["score"] > (best[1]["score"] if best else base):
                best = (trial, k)
        if best is None:
            return config
        trial, k = best
        out["kept"] = {"table": k["table"], "column": k["column"]}
        entry = {"config_id": trial["config_id"], "actions": trial["actions"], "partition": out["kept"],
                 **{f: k[f] for f in ("twin", "measured_drop", "measured_reward", "score")}}
        if chosen:
            keep = ("config_id", "actions", "twin", "measured_drop", "measured_reward", "score")
            chosen.update(entry, without_partition={f: chosen[f] for f in keep})
        else:   # no index or rewrite paid for itself: the partition alone
            self.trace.top_configs.append({"cand_ids": [], "return": 0.0, "predicted_ms": round(self.trace.baseline_ms, 3),
                                           "predicted_drop": 0.0, "hypopg_cost_drop": 0.0, "disagreement": 0.0,
                                           **entry, "chosen": True})
        return trial

    def recheck(self) -> dict:
        """The doc's final choice over self.top (set by run()): raw HypoPG cost next to the
        estimator, a twin measurement each, and the best measured score wins. Every entry, with
        its numbers, replaces trace.top_configs. A config whose best score is not above 0 (the
        empty configuration's) loses to no change. A config the twin cannot measure (plan
        disagreement, 409) is reported and not chosen; if none can be measured, the best
        predicted configuration stays."""
        w0, r0 = self.cost([])[0], self._raw[frozenset()]
        entries = []
        for opts, summary in zip(self.top, self.trace.top_configs):
            ms, _ = self.cost(opts)
            key = frozenset(o["cand_id"] for o in opts)
            drop_est = 1 - ms / w0 if w0 else 0.0
            drop_raw = 1 - self._raw[key] / r0 if r0 else 0.0
            config = _config([_action(o) for o in opts], "q_learning")
            e = {**summary, "config_id": config["config_id"], "actions": config["actions"],
                 "predicted_drop": round(drop_est, 4), "hypopg_cost_drop": round(drop_raw, 4),
                 "disagreement": round(abs(drop_est - drop_raw), 4), "opts": opts}
            try:
                sim, cached = twin(config)
            except httpx.HTTPStatusError as err:
                entries.append({**e, "twin_error": err.response.status_code})
                continue
            indexes = [o for o in opts if not _is_rewrite(o)]
            entries.append({**e, **self._measured(sim, cached, len(indexes), {o["table"] for o in indexes}, e["disagreement"])})
        measured = [e for e in entries if "score" in e]
        best = max(measured, key=lambda e: e["score"], default=None)
        if best is not None and best["score"] <= 0:
            best = None   # nothing pays for itself when measured: keep the empty configuration (score 0)
        self.trace.final_choice = ("best measured on the twin" if measured
                                   else "best predicted (no twin measurement succeeded)")
        self.trace.top_configs = [{**{k: v for k, v in e.items() if k != "opts"}, "chosen": e is best} for e in entries]
        if not measured:
            return self._finish(self.best_predicted, "q_learning")
        return self._finish(best["opts"] if best else [], "q_learning")


def run(weights: dict[str, float] | None = None) -> tuple[dict, Trace]:
    """Fetch hashed inputs from the gateway, mine candidates (original and rewritten shapes),
    check the matching rewrites, calibrate the predictor on the measured plans, search, and
    re-check the top configurations on the twin. Returns (Config, Trace)."""
    global _WORKLOAD
    templates = gw.get("/v1/templates/slow")
    _WORKLOAD = frozenset(t["template_id"] for t in templates)
    column_meta = gw.get("/v1/meta/columns")
    table_meta = gw.get("/v1/meta/tables")
    rewrites = gw.get("/v1/rewrite/candidates")
    existing = [(c["table"], [c["col"]]) for c in column_meta if c["bits"]["pk"]]
    shapes = fpgrowth.with_rewritten_shapes(templates, rewrites)
    candidates = fpgrowth.candidates(shapes, column_meta, existing)
    rw_options, rw_checks = rewrite_options(rewrites)
    options = candidates + rw_options
    measured = [p for t in templates for p in gw.get(f"/v1/templates/{t['template_id']}/plans")]
    model = pred.load_predictor().fit(measured)
    rl = QLearningSearch(templates, column_meta, table_meta, model, weights)
    rl._hypo = _HYPO
    rl.trace.rewrites = rw_checks
    predicted = rl.run(options)
    # The doc's comparison: greedy on the same cost cache, reported next to the RL result.
    greedy = GreedySearch(templates, column_meta, table_meta, model, weights)
    greedy._cache, greedy._raw, greedy._hypo = rl._cache, rl._raw, _HYPO
    g = greedy.run(options)
    config = rl.recheck()
    rl.trace.greedy = {"config_id": g["config_id"], "cand_ids": [s["cand_id"] for s in greedy.trace.steps],
                       "predicted_ms": round(greedy.trace.final_ms, 3), "same_as_rl": g["config_id"] == config["config_id"],
                       "same_as_rl_before_twin": g["config_id"] == predicted["config_id"]}
    # After both searches and the re-check (doc): partition keys, measured on the twin only.
    return rl.add_partition(config, partition_keys(shapes, column_meta, table_meta)), rl.trace
