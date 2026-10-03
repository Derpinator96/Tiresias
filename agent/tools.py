"""The LLM's tools: all eight of the doc's. Each is a thin wrapper over one endpoint and
returns hashed data only. Rewrites: the AI picks a rule; the gateway applies it to the real
SQL and verifies it privately (VeriEQL plus a twin checksum).

Each call gets an ID tc_ plus 8 hex; the result is kept under that ID so the number checker
can trace every number in the answer back to it.
"""
from __future__ import annotations

import secrets
from typing import Callable

from agent import gateway_client as gw
from common.config import cfg

DECLARATIONS = [
    {"name": "get_slow_templates", "description": "Top query templates by total time, hashed.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_plan", "description": "Latest executed plan of one template, with measured per-node times.",
     "parameters": {"type": "object", "properties": {"template_id": {"type": "string"}}, "required": ["template_id"]}},
    {"name": "mine_candidates", "description": "Candidate indexes mined from the slow workload, with support.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "run_rl", "description": "Search for the best index configuration. Returns a config_id, its actions and predicted times.",
     "parameters": {"type": "object", "properties": {"template_ids": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "gnn_explain", "description": "Why one template's latest plan is slow: the plan nodes with the largest "
     "predicted share of time (from the serving runtime estimator), and nodes where Postgres's row estimate was off "
     "by the alert ratio or more, with an ANALYZE recommendation.",
     "parameters": {"type": "object", "properties": {"template_id": {"type": "string"}}, "required": ["template_id"]}},
    {"name": "rewrite_candidates", "description": "Rewrite rules that fit each slow template's shape, with the "
     "rewritten hashed SQL (values shown as ?). Not yet checked.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "verify", "description": "Check one rewrite: the gateway applies the rule to the real query and runs an "
     "equivalence verifier and a result checksum on the twin. Returns status Verified, TestedOnly or Rejected.",
     "parameters": {"type": "object", "properties": {"template_id": {"type": "string"}, "rule_id": {"type": "string"}},
                    "required": ["template_id", "rule_id"]}},
    {"name": "simulate", "description": "Measure a configuration on the statistical twin: before and after ms, storage MB.",
     "parameters": {"type": "object", "properties": {"config_id": {"type": "string"}}, "required": ["config_id"]}},
]


class Toolbox:
    def __init__(self):
        self.results: dict[str, object] = {}      # tool_call_id -> result
        self.calls: list[dict] = []               # [{tool_call_id, name}]
        self.configs: dict[str, dict] = {}        # config_id -> Config from run_rl

    def get_slow_templates(self) -> object:
        return gw.get("/v1/templates/slow")

    def get_plan(self, template_id: str) -> object:
        plans = gw.get(f"/v1/templates/{template_id}/plans")
        return plans[0] if plans else {"error": "no logged plan for this template"}

    def mine_candidates(self) -> object:
        from agent.api import mine
        return mine()

    def run_rl(self, template_ids: list[str] | None = None) -> object:
        from rl import search
        config, trace = search.run()
        self.configs[config["config_id"]] = config
        return {"config": config, "label": search.LABEL,
                "baseline_predicted_ms": round(trace.baseline_ms, 3), "final_predicted_ms": round(trace.final_ms, 3),
                "greedy_baseline": trace.greedy}

    def gnn_explain(self, template_id: str) -> object:
        from agent.api import calibrated_predictor
        plan = self.get_plan(template_id)
        if "error" in plan:
            return plan
        model = calibrated_predictor([plan])
        p = model.predict(plan)
        nodes = {n["node_id"]: n for n in plan["nodes"]}
        top = sorted(p["nodes"], key=lambda n: -n["share"])[:3]
        alert = float(cfg("gnn.misestimate_ratio_alert"))
        mis = []
        for n in plan["nodes"]:
            if "actual_rows" in n:
                lo, hi = sorted((max(n["est_rows"], 1), max(n["actual_rows"], 1)))
                if hi / lo >= alert:
                    mis.append({"node_id": n["node_id"], "op": n["op"], "relation": n.get("relation"),
                                "est_rows": n["est_rows"], "actual_rows": n["actual_rows"],
                                "ratio": round(hi / lo, 1), "recommend": "ANALYZE the relation to refresh its statistics"})
        return {"estimator": p["estimator"], "label": model.label, "predicted_total_ms": p["total_ms"],
                "top_nodes": [{"node_id": n["node_id"], "op": nodes[n["node_id"]]["op"],
                               "relation": nodes[n["node_id"]].get("relation"),
                               "predicted_share_pct": round(100 * n["share"], 1),
                               "predicted_self_ms": n["self_ms"]} for n in top],
                "misestimate_alert_ratio": alert, "misestimates": mis}

    def rewrite_candidates(self) -> object:
        return gw.get("/v1/rewrite/candidates")

    def verify(self, template_id: str, rule_id: str) -> object:
        return gw.post("/v1/rewrite/verify", {"template_id": template_id, "rule_id": rule_id})

    def simulate(self, config_id: str) -> object:
        config = self.configs.get(config_id)
        if config is None:
            return {"error": f"unknown config_id {config_id}; call run_rl first"}
        sim = gw.post("/v1/simulate/twin", config)
        # Speedups computed here, by code, so the LLM can cite them instead of computing them.
        for t in sim["templates"]:
            t["speedup_pct"] = round(100 * (1 - t["after_ms"] / t["before_ms"]), 1) if t["before_ms"] else 0.0
        return sim

    def call(self, name: str, args: dict) -> tuple[str, object]:
        fn: Callable | None = getattr(self, name, None) if name in {d["name"] for d in DECLARATIONS} else None
        tc = "tc_" + secrets.token_hex(4)
        try:
            result = fn(**(args or {})) if fn else {"error": f"unknown tool {name}"}
        except Exception as e:   # a failed tool is reported to the model, not raised
            result = {"error": f"{name} failed: {type(e).__name__}"}
        self.results[tc] = result
        self.calls.append({"tool_call_id": tc, "name": name})
        return tc, result
