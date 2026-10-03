"""Blind Tuner operator dashboard (Streamlit). Private: bound to 127.0.0.1, shows real names,
never hosted publicly. Every simplified component carries its label on screen, and every
number shown comes from a gateway or ai response on this page."""
from __future__ import annotations

import json
import threading

import streamlit as st

from dashboard import data

st.set_page_config(page_title="Blind Tuner operator dashboard", layout="wide")

@st.cache_resource
def _jobs() -> dict[str, dict]:
    """question_id -> {"done": bool, "status": int, "body": dict}. Cached as a resource so it
    survives reruns: Streamlit re-executes this script on every interaction."""
    return {}


JOBS = _jobs()


def view(text: str) -> str:
    return text if st.session_state.get("ai_view") else data.dehash(text)


st.title("Blind Tuner operator dashboard")
st.caption("Runs on 127.0.0.1 inside the private network. This page shows real table and column names, "
           "so it is never hosted publicly.")

estimator = data.estimator_label()   # names the estimator the ai service is serving now
with st.container(border=True):
    st.markdown("**Simplified components in this build**")
    st.markdown(f"- {estimator}")
    for key in ("search", "twin", "verify", "write_cost", "egress"):
        st.markdown(f"- {data.LABELS[key]}")

st.toggle("Show what the AI sees (hashed codes) instead of what the DBA sees (real names)", key="ai_view")

# ---- Ask ---------------------------------------------------------------------------------
st.header("Ask about a slow dashboard")
question = st.text_input("Question", value="Why is the weekly sales dashboard timing out?")
if st.button("Ask", type="primary"):
    res = data.gateway("/v1/ask/resolve", {"question": question})
    st.session_state["resolved"] = res
    qid = res["question_id"]
    JOBS[qid] = {"done": False}

    def run(qid=qid, tids=res["template_ids"]):
        r = data.ai("/ai/ask", {"question_id": qid, "template_ids": tids})
        JOBS[qid] = {"done": True, "status": r.status_code, "body": r.json()}
    threading.Thread(target=run, daemon=True).start()
    st.session_state["qid"] = qid

if "resolved" in st.session_state:
    res = st.session_state["resolved"]
    st.markdown(f"Resolved locally to question `{res['question_id']}` and templates "
                f"`{', '.join(res['template_ids']) or 'none'}`. The question text itself was not sent to the AI.")
    if res.get("question_had_canary"):
        st.warning("The question contained a canary token. It stayed inside the gateway; only the IDs above left.")


@st.fragment(run_every="1s")
def answer_panel():
    qid = st.session_state.get("qid")
    if not qid:
        return
    job = JOBS.get(qid, {})
    events = data.ai(f"/ai/ask/{qid}/events", method="GET").json()["events"]
    for e in events:
        if e.startswith(("rate limited", "LLM service unavailable")):
            st.warning(e)
    if not job.get("done"):
        st.info(f"Agent working: {len([e for e in events if e.startswith('tool ')])} tool calls so far")
        return
    body = job["body"]
    if job["status"] != 200:
        detail = body.get("detail")
        st.error(f"Agent did not answer: {detail if isinstance(detail, str) else json.dumps(detail)}")
        return
    if body["status"] != "ok":
        st.error("Answer blocked by the number checker: it contained numbers not found in any tool result "
                 f"({', '.join(body['unmatched'])}).")
        return
    st.success(view(body["answer"]["text"]))
    st.caption("Every number above passed the number checker: each one appears in the tool result it cites. "
               "Tool calls: " + ", ".join(f"{c['name']} ({c['tool_call_id']})" for c in body["tool_calls"]))


answer_panel()

# ---- Slow templates and plan ---------------------------------------------------------------
st.header("Slow query templates")
slow = data.gateway("/v1/templates/slow")
if not slow:
    st.info("No template is slower than the configured threshold (workload.slow_query_ms). Run make seed.")
else:
    st.dataframe([{"template": view(t["template_id"]), "query": view(t["sql"]), "calls": t["calls"],
                   "mean ms": t["mean_ms"], "total ms": t["total_ms"]} for t in slow], hide_index=True)

    top = slow[0]
    st.header("Plan of the slowest template")
    plans = data.gateway(f"/v1/templates/{top['template_id']}/plans")
    if plans:
        pr = data.ai("/ai/gnn/predict", [plans[0]])
        prediction = pr.json()[0] if pr.status_code == 200 else None
        st.graphviz_chart(data.plan_dot(plans[0], prediction, view))
        st.caption(f"Measured self times from the auto_explain log. Predicted shares from the {estimator}. "
                   "Node colour: grey (small predicted share) to red (large).")

# ---- Recommendation, twin, verification -----------------------------------------------------
st.header("Recommended configuration")
st.caption(data.LABELS["search"])
if st.button("Run search"):
    st.session_state["rl"] = data.ai("/ai/rl/run", {}).json()
    st.session_state.pop("twin", None)
rl = st.session_state.get("rl")
if rl:
    if not rl["config"]["actions"]:
        st.info("The search found no index worth its write and storage cost.")
    for a in rl["config"]["actions"]:
        cols = ", ".join(view(c) for c in a["columns"])
        st.markdown(f"Add index on **{view(a['table'])} ({cols})**: predicted saving "
                    f"{a['contribution']['predicted_ms_saved']:.1f} ms per call ({rl.get('estimator_label', estimator)})")
    st.caption(f"Predicted workload time {rl['baseline_predicted_ms']:.1f} ms before, {rl['final_predicted_ms']:.1f} ms after. "
               "Predictions rank candidates; the twin measurement below is the reported result.")
    g = rl.get("greedy") or {}
    if g:
        st.caption(f"Greedy baseline on the same predictions: {g['predicted_ms']:.1f} ms after, "
                   + ("the same configuration as Q-learning." if g["same_as_rl"] else "a different configuration from Q-learning.")
                   + f" Q-learning ran {rl['episodes']} episodes.")

    st.header("Measured on the twin")
    if st.button("Measure on twin"):
        sim = data.gateway("/v1/simulate/twin", rl["config"])
        chk = data.gateway("/v1/twin/checksum", {"template_id": sim["templates"][0]["template_id"], "config": rl["config"]})
        st.session_state["twin"] = (sim, chk)
    if "twin" in st.session_state:
        sim, chk = st.session_state["twin"]
        tables = {t["table"]: t["rows"] for t in data.gateway("/v1/meta/tables")}
        hero = rl["config"]["actions"][0]["table"] if rl["config"]["actions"] else None
        for t in sim["templates"]:
            speedup = 100 * (1 - t["after_ms"] / t["before_ms"]) if t["before_ms"] else 0.0
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Before (measured)", f"{t['before_ms']:.1f} ms")
            c2.metric("After (measured)", f"{t['after_ms']:.1f} ms")
            c3.metric("Faster by", f"{speedup:.0f}%")
            c4.metric("Index storage", f"{sim['storage_mb_delta']} MB")
        if hero:
            st.markdown(f"Assumptions: {view(hero)}: {tables.get(hero, 0):,} rows, demo scale, not production size. "
                        f"Median of {sim['runs']} warm runs on the twin, same machine before and after. "
                        f"{data.LABELS['twin']}. {data.LABELS['write_cost']}.")
        st.markdown(f"Verification: **{'TestedOnly' if chk['match'] else 'Rejected'}**: result checksum on the twin "
                    f"{'matches' if chk['match'] else 'differs'} with the index (VeriEQL checks rewrites, not indexes).")

# ---- Privacy -------------------------------------------------------------------------------
st.header("Privacy")
led = data.gateway("/v1/ledger")
c1, c2, c3 = st.columns(3)
c1.metric("Payloads to the AI side", f"{led['outbound_payloads']:,}")
c2.metric("Canary hits in those payloads", f"{led['outbound_canary_hits']}")
c3.metric("Canaries planted", f"{led['canaries_planted']}")
st.caption("Counts every response of the AI-facing API and every LLM request body, including this page's own reads "
           "of the same endpoints. A payload with a hit is blocked, not sent.")
if st.button("Run negative control"):
    st.session_state["control"] = data.gateway("/v1/privacy/negative-control", {})
if "control" in st.session_state:
    e = st.session_state["control"]
    st.error(f"Negative control: the same logs with the gateway's hashing and stripping switched off hold "
             f"{len(e['canary_hits'])} canary hits. Scanned locally only, never sent.")
st.download_button("Export payload ledger (JSON)", json.dumps(led["entries"], indent=1),
                   file_name="payload_ledger.json", mime="application/json")

# ---- Rewrites ------------------------------------------------------------------------------
st.header("Rewrites")
st.caption(f"{data.LABELS['rewrite_rules']}. The AI picks a rule by the query's shape; the gateway applies it to the "
           f"real query and checks it privately ({data.LABELS['verify']}).")
cands = data.gateway("/v1/rewrite/candidates")
if not cands:
    st.info("No slow template has a shape any rewrite rule fits.")
if cands and st.button("Verify rewrites"):
    st.session_state["rewrites"] = {(c["template_id"], c["rule_id"]): data.gateway(
        "/v1/rewrite/verify", {"template_id": c["template_id"], "rule_id": c["rule_id"]}) for c in cands}
done = st.session_state.get("rewrites", {})
for c in cands:
    rw = done.get((c["template_id"], c["rule_id"]))
    status = rw["status"] if rw else "not checked yet"
    st.markdown(f"**{c['rule_id']}** on {view(c['template_id'])}: **{status}**"
                + (f" (VeriEQL: {rw['checks']['verieql']}, twin checksum: {rw['checks']['checksum']})" if rw else ""))
    st.code(view(c["sql"]), language="sql")
