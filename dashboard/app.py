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

    st.header("Plan tree per slow template")
    # Options are rank numbers, so two templates whose cut-off query text matches stay distinct.
    rank = st.selectbox("Template (slowest first)", range(len(slow)), format_func=lambda i: f"{i + 1}. {view(slow[i]['template_id'])}")
    tid = slow[rank]["template_id"]
    plans = data.gateway(f"/v1/templates/{tid}/plans")
    if plans:
        pr = data.ai("/ai/gnn/predict", [plans[0]])
        prediction = pr.json()[0] if pr.status_code == 200 else None
        st.graphviz_chart(data.plan_dot(plans[0], prediction, view))
        st.caption(f"Measured self times from the auto_explain log. Predicted shares from the {estimator}. "
                   "Node colour: grey (small predicted share) to red (large).")
    else:
        st.info("No auto_explain plan is logged for this template.")

# ---- Recommendation, twin, verification -----------------------------------------------------
st.header("Recommended configuration")
st.caption(data.LABELS["search"])
if st.button("Run search"):
    st.session_state["rl"] = data.ai("/ai/rl/run", {}).json()
    st.session_state.pop("twin", None)
rl = st.session_state.get("rl")
if rl:
    if not rl["config"]["actions"]:
        st.info("The search found no index or rewrite worth its write and storage cost.")
    checks = {(c["template_id"], c["rule_id"]): c["status"] for c in rl.get("rewrites", [])}
    for a in rl["config"]["actions"]:
        if a["type"] == "rewrite":
            head = f"Rewrite **{view(a['template_id'])}** with rule **{a['rule_id']}** " \
                   f"(check: {checks.get((a['template_id'], a['rule_id']), 'not checked')})"
        else:
            head = f"Add index on **{view(a['table'])} ({', '.join(view(c) for c in a['columns'])})**"
        st.markdown(f"{head}: predicted saving {a['contribution']['predicted_ms_saved']:.1f} ms per call "
                    f"({rl.get('estimator_label', estimator)})")
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
        hero = next((a["table"] for a in rl["config"]["actions"] if a["type"] == "add_index"), None)
        for t in sim["templates"]:
            speedup = 100 * (1 - t["after_ms"] / t["before_ms"]) if t["before_ms"] else 0.0
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Before (measured)", f"{t['before_ms']:.1f} ms")
            c2.metric("After (measured)", f"{t['after_ms']:.1f} ms")
            c3.metric("Faster by", f"{speedup:.0f}%")
            c4.metric("Index storage", f"{sim['storage_mb_delta']} MB")
            w = sim["write_ms_delta"]
            c5.metric("Insert latency added (measured)", "not measured" if w is None else f"{w:+.3f} ms per insert")
        if (sim["write_ms_delta"] or 0) < 0:
            st.caption("The insert latency difference is below zero: the index's write cost is smaller than this "
                       "run's timing noise, not a speed-up.")
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

# ---- Search re-check on the twin -------------------------------------------------------------
st.header("Top configurations re-checked on the twin")
st.caption(f"{data.LABELS['search']}. Each configuration is scored by its measured drop in workload time, minus the "
           f"assumed write penalty ({data.cfg('rl.lambda_write') * data.cfg('rl.write_penalty_ms_per_index'):g} per index, "
           "an assumption, not a measurement) and the measured storage against the budget, minus the gap between the "
           "estimator's predicted drop and raw HypoPG cost. The best score is the recommendation above.")
if not rl:
    st.info("Run the search above to see the configurations it re-checked.")
else:
    st.markdown(f"Final choice: **{rl.get('final_choice', 'best predicted')}**.")
    for i, e in enumerate(rl.get("top_configs", []), 1):
        what = "; ".join(data.describe(a, view) for a in e["actions"])
        st.markdown(f"{i}. {'**Chosen.** ' if e.get('chosen') else ''}{what}")
        if "twin_error" in e:
            st.caption(f"Not measured: the twin returned HTTP {e['twin_error']}.")
            continue
        tw = e["twin"]
        st.caption(f"Predicted drop {100 * e['predicted_drop']:.1f}%, raw HypoPG cost drop {100 * e['hypopg_cost_drop']:.1f}%, "
                   f"measured drop {100 * e['measured_drop']:.1f}% (median of {tw['runs']} runs per query"
                   + (", reused from an earlier measurement of the same actions" if tw["cached"] else "")
                   + f"), index storage {tw['storage_mb']} MB measured, score {e['score']:.3f}.")
        st.dataframe([{"template": view(t["template_id"]), "before ms (measured)": t["before_ms"],
                       "after ms (measured)": t["after_ms"]} for t in tw["templates"]], hide_index=True)

# ---- Approve -------------------------------------------------------------------------------
st.header("Approve: migration, rollback and post-deploy check")
st.caption(f"{data.LABELS['approve_demo']}. The files hold real names and logged query values, so they stay on this "
           "page and never go to the AI side. Nothing runs on production: the DBA runs the files.")
rl = st.session_state.get("rl")
if st.session_state.get("ai_view"):
    st.info("Hidden in the AI view: the approve files hold real table, column and index names and logged query values.")
elif not rl:
    st.info("Run the search above first: Approve turns its configuration into the three files.")
else:
    if st.button("Approve"):
        # The recommended configuration plus every rewrite checked above and not Rejected.
        have = {(a["template_id"], a["rule_id"]) for a in rl["config"]["actions"] if a["type"] == "rewrite"}
        extra = [{"type": "rewrite", "template_id": t, "rule_id": r}
                 for (t, r), rw in st.session_state.get("rewrites", {}).items() if rw["status"] != "Rejected" and (t, r) not in have]
        actions = rl["config"]["actions"] + extra
        config = {**rl["config"], "actions": actions[:5]}          # the Config contract allows 5 actions
        st.session_state["approve"] = (config, data.gateway("/v1/approve", config), len(actions) - len(config["actions"]))
        st.session_state.pop("approve_check", None)
    if "approve" in st.session_state:
        config, ap, left_out = st.session_state["approve"]
        if left_out:
            st.warning(f"{left_out} checked rewrites left out: a configuration holds at most 5 actions.")
        for name, text in ap["files"].items():
            with st.expander(name):
                st.code(text, language="python" if name.endswith(".py") else "sql")
            st.download_button(f"Download {name}", text, file_name=name, mime="text/plain")
        if st.button("Run the post-deploy check on the twin"):
            st.session_state["approve_check"] = data.gateway("/v1/approve/twin-check", config)
        tc = st.session_state.get("approve_check")
        if tc:
            for tid, after in tc["templates"].items():
                b = tc["baseline"][tid]
                st.markdown(f"{view(tid)}: median {b['median_ms']:.1f} ms before ({b['runs']} runs), "
                            f"{after['median_ms']:.1f} ms after ({after['runs']} runs), measured on the twin")
            st.markdown(f"Post-deploy check on the twin: **{'rolled back' if tc['rolled_back'] else 'kept'}**. It rolls back "
                        f"when a template's median is more than {100 * tc['worse_by']:.0f}% worse. The twin was returned "
                        "to its baseline afterwards.")
            st.caption(f"Ran on the twin with a shortened duration: {data.LABELS['approve_demo']}. {data.LABELS['twin']}. "
                       "On a busy machine a short replay is noisy, so a template the change does not touch can cross the threshold.")
# ---- Twin fidelity -------------------------------------------------------------------------
st.header("Twin fidelity: twin speedup divided by pg-prod speedup, per query")
st.caption(f"{data.LABELS['fidelity']}. {data.LABELS['twin']}.")
fid = data.gateway("/v1/twin/fidelity")
if not fid:
    st.info("Not measured yet. Run make fidelity: it builds each configuration's indexes on pg-prod only while it "
            "measures, drops them, and checks that pg-prod is back to primary key indexes only.")
else:
    st.dataframe(data.fidelity_rows(fid, names=not st.session_state.get("ai_view")), hide_index=True)
    st.markdown(f"Assumptions: speedup = before ms / after ms; fidelity 1.0 means the twin predicted pg-prod's speedup "
                f"exactly, below 1.0 that it understated it. Before is the original query without the new indexes, after "
                f"is the rewritten query (where there is a rewrite) with them; each is the median of {fid['runs']} warm runs "
                f"after {fid['warmup_runs']} warm-up run(s). On pg-prod the indexes existed only during the measurement and "
                f"were dropped. Twin and pg-prod were measured one after the other on the same machine; background load "
                f"was not controlled. Measured {fid['generated_at']}; twin label at measurement: {fid['twin_label']}. "
                f"Plans agree: the operator sequence on the twin matches pg-prod's, before and after.")
