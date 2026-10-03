"""Dashboard data access and plan drawing. Private side: this module may show real names,
which is why the dashboard is bound to 127.0.0.1 and never hosted publicly."""
from __future__ import annotations

import json
import os
import threading

import httpx

from common.config import REPO_ROOT, cfg

TIMEOUT_S = 300.0

# On-screen labels for simplified or missing parts. The text matches the modules that own them.
LABELS = {
    "estimator": "estimator: Postgres cost x calibration (GNN pending)",
    "search": (f"search: Q-learning over index and rewrite actions, top {cfg('rl.configs_verified_on_twin')} "
               "re-checked on the twin (partition and drop-index actions pending)"),
    "twin": "twin: synthetic from pg_stats, correlations kept only for column pairs the miner flags",
    "verify": f"verification: VeriEQL up to {cfg('verify.verieql_rows_per_table')} rows per table plus a result checksum on the twin",
    "rewrite_rules": "rewrite rules: 3 built-in rules (R-Bot rule retrieval pending)",
    "egress": "AI egress: allowlist proxy, CONNECT to the LLM API host only (checks the host name, not the traffic inside TLS)",
    # Same text as db/sandbox/write_cost.LABEL (db/sandbox/tests/test_write_cost.py checks it).
    "write_cost": (f"write cost: pgbench on the twin, {cfg('sandbox.pgbench_insert_rate_per_s')} inserts/s for "
                   f"{cfg('sandbox.pgbench_duration_s')} s, median INSERT latency with minus without the indexes "
                   "(WAL flush wait excluded)"),
    "approve_demo": (f"post-deploy check demo: runs on the twin with a shortened replay of {cfg('approve.demo_check_minutes')} "
                     f"minutes per phase (production: {cfg('approve.post_deploy_check_minutes')} minutes)"),
    "fidelity": "fidelity: configurations from config.yaml (the doc's expected picks), not from a live search run",
    "miner": "miner: covered-index check knows primary keys only",
    "adversarial": "adversarial leak test: a fresh LLM session guesses table and column names from one run's payloads "
                   "(values not scored; plaintext LLM control pending air-gapped mode)",
}


def estimator_label() -> str:
    """The label of the estimator the ai service is serving right now (GNN or the calibrated
    Postgres baseline). Falls back to the baseline's label if ai cannot say."""
    try:
        r = ai("/ai/gnn/estimator")
        return r.json()["label"] if r.status_code == 200 else LABELS["estimator"]
    except httpx.HTTPError:
        return LABELS["estimator"]


def describe(action: dict, name=lambda code: code) -> str:
    """One Config action in words, names through `name` (dehash or identity)."""
    if action["type"] == "rewrite":
        return f"Rewrite {name(action['template_id'])} with rule {action['rule_id']}"
    return f"Add index on {name(action['table'])} ({', '.join(name(c) for c in action['columns'])})"


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


def fidelity_rows(doc: dict, names: bool) -> list[dict]:
    """Table rows for the fidelity panel from the make fidelity result. The file holds no names;
    with names on, each query's configuration is read from config.yaml (sandbox.fidelity_queries)."""
    cases = cfg("sandbox.fidelity_queries")
    rows = []
    for q in doc["queries"]:
        if names and q["query"] in cases:
            setup = "; ".join(f"index on {t} ({', '.join(c)})" for t, c in cases[q["query"]]["indexes"])
        else:
            setup = f"{q['indexes']} index(es), names hidden"
        if q["rewrite"]:
            setup = f"rewrite {q['rewrite']}; {setup}"
        tw, pr = q["twin"], q["production"]
        rows.append({"query": q["query"], "configuration": setup,
                     "twin before ms": tw["before_ms"], "twin after ms": tw["after_ms"], "twin speedup": tw["speedup"],
                     "pg-prod before ms": pr["before_ms"], "pg-prod after ms": pr["after_ms"], "pg-prod speedup": pr["speedup"],
                     "fidelity": q["fidelity"],
                     "plans agree before / after": f"{'yes' if q['plan_agrees']['before'] else 'no'} / "
                                                   f"{'yes' if q['plan_agrees']['after'] else 'no'}"})
    return rows


def adversarial() -> dict | None:
    """The last adversarial leak test result: runs/adversarial.json, written by make adversarial
    (privacy_tests/adversarial.py). Counts and match flags only, no names. None until it ran."""
    try:
        return json.loads((REPO_ROOT / "runs" / "adversarial.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def start_background(fn, *args) -> None:
    """Run fn(*args) in a daemon thread. A separate function so tests can run it inline."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def sql_statements(text: str) -> str:
    """The runnable SQL in an approve file (migration.sql or rollback.sql), without its comments.
    A rewrite action is a suggested code change, not SQL to run, so approve writes it as comments;
    its rewritten query is taken from the commented block that follows "Rewritten:"."""
    out, in_rewrite = [], False
    for line in text.splitlines():
        if line.strip().startswith("--    Rewritten:"):
            in_rewrite = True
            out.append("-- rewritten query (application code change)")
            continue
        if in_rewrite and line.startswith("--      "):
            out.append(line[len("--      "):])
            continue
        in_rewrite = False
        if line.strip() and not line.lstrip().startswith("--"):
            out.append(line)
    return "\n".join(out)


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
