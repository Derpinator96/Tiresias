"""Dashboard data access and plan drawing. Private side: this module may show real names,
which is why the dashboard is bound to 127.0.0.1 and never hosted publicly."""
from __future__ import annotations

import os

import httpx

from common.config import cfg

TIMEOUT_S = 300.0

# On-screen labels for simplified or missing parts. The text matches the modules that own them.
LABELS = {
    "estimator": "estimator: Postgres cost x calibration (GNN pending)",
    "search": "search: Q-learning, index actions only (rewrite, partition and top-3 twin re-check pending)",
    "twin": "twin: synthetic from pg_stats, no column correlations yet",
    "verify": f"verification: VeriEQL up to {cfg('verify.verieql_rows_per_table')} rows per table plus a result checksum on the twin",
    "rewrite_rules": "rewrite rules: 3 built-in rules (R-Bot rule retrieval pending)",
    "egress": "AI egress: SIMPLIFIED, unrestricted internet (LLM host allowlist pending)",
    "write_cost": "write cost: not measured (pgbench pending)",
}


def estimator_label() -> str:
    """The label of the estimator the ai service is serving right now (GNN or the calibrated
    Postgres baseline). Falls back to the baseline's label if ai cannot say."""
    try:
        r = ai("/ai/gnn/estimator")
        return r.json()["label"] if r.status_code == 200 else LABELS["estimator"]
    except httpx.HTTPError:
        return LABELS["estimator"]


LLM_UNKNOWN = "LLM: unknown (the ai service did not say which model answers)"


def llm_info() -> dict:
    """Which LLM the ai service uses now: its label (agent/llm.py) and whether ai checked that
    it cannot reach the LLM API host (air-gapped mode)."""
    try:
        r = ai("/ai/llm")
        return r.json() if r.status_code == 200 else {"label": LLM_UNKNOWN}
    except httpx.HTTPError:
        return {"label": LLM_UNKNOWN}


def gateway(path: str, body=None, method: str | None = None):
    url = os.environ["GATEWAY_URL"].rstrip("/") + path
    r = httpx.request(method or ("POST" if body is not None else "GET"), url, json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def ai(path: str, body=None, method: str | None = None) -> httpx.Response:
    url = os.environ["AI_URL"].rstrip("/") + path
    return httpx.request(method or ("POST" if body is not None else "GET"), url, json=body, timeout=TIMEOUT_S)


def dehash(text: str) -> str:
    """Real names for codes, via the gateway's private vault."""
    return gateway("/v1/answers/dehash", {"question_id": "qn_00000000", "text": text, "numbers": []})["text"]


def heat(share: float) -> str:
    """Grey to red by predicted share of time. No purple."""
    s = max(0.0, min(1.0, share))
    r, g, b = int(235 - 35 * s), int(235 - 170 * s), int(235 - 170 * s)
    return f"#{r:02x}{g:02x}{b:02x}"


def plan_dot(plan: dict, prediction: dict | None, name=lambda code: code) -> str:
    """Graphviz DOT for a HashedPlan: data flows bottom-up, so edges point child -> parent.
    Each node shows its operator, relation, measured self time and predicted share."""
    shares = {n["node_id"]: n["share"] for n in (prediction or {}).get("nodes", [])}
    lines = ['digraph plan {', 'rankdir=BT;', 'node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=11];']
    for n in plan["nodes"]:
        label = [n["op"]]
        if n.get("relation"):
            label.append(f"on {name(n['relation'])}")
        if n.get("index"):
            label.append(f"index {name(n['index'])}")
        if n.get("filter_cols"):
            label.append("filter: " + ", ".join(name(c) for c in n["filter_cols"]))
        if "self_ms" in n:
            label.append(f"measured self time {n['self_ms']:.1f} ms")
        if n["node_id"] in shares:
            label.append(f"predicted share {100 * shares[n['node_id']]:.0f}%")
        text = "\\n".join(s.replace('"', "'") for s in label)
        lines.append(f'n{n["node_id"]} [label="{text}", fillcolor="{heat(shares.get(n["node_id"], 0.0))}"];')
        if n["parent_id"] is not None:
            lines.append(f'n{n["node_id"]} -> n{n["parent_id"]};')
    lines.append("}")
    return "\n".join(lines)
