"""Ask page: a question in, then the LLM's answer, the time saved measured on the twin, and the
SQL to apply and to roll back. Every number comes from a gateway or ai response."""
from __future__ import annotations

import json

import streamlit as st

from common.config import cfg
from dashboard import data


@st.cache_resource
def _jobs() -> dict[str, dict]:
    """question_id -> job state. A resource cache survives Streamlit's rerun on every click."""
    return {}


JOBS = _jobs()


def view(text: str) -> str:
    return text if st.session_state.get("ai_view") else data.dehash(text)


def run_job(qid: str, tids: list[str]) -> None:
    """Background work for one question: the agent's answer, then the configuration and twin
    measurement it used (or a fresh search and measurement if it made none), then the SQL."""
    job = JOBS[qid]
    try:
        r = data.ai("/ai/ask", {"question_id": qid, "template_ids": tids})
        try:
            body = r.json()
        except ValueError:
            body = {"detail": f"HTTP {r.status_code} from the ai service"}
        job["ask"] = (r.status_code, body)
        ok = r.status_code == 200
        config = body.get("config") if ok else None
        sim = body.get("simulation") if ok else None
        if not config or not config["actions"]:
            rl = data.ai("/ai/rl/run", {})
            if rl.status_code != 200:
                raise RuntimeError(f"the search failed (HTTP {rl.status_code} from the ai service)")
            config, sim = rl.json()["config"], None
        if config["actions"]:
            if sim is None:
                sim = data.gateway("/v1/simulate/twin", config)
            job["files"] = data.gateway("/v1/approve", config)["files"]
            job["rows"] = {t["table"]: t["rows"] for t in data.gateway("/v1/meta/tables")}
        job.update(config=config, sim=sim)
    except Exception as e:      # shown on the page; a dead thread would leave it waiting forever
        job.setdefault("ask", (0, {"detail": "not reached"}))
        job["error"] = str(e) or type(e).__name__
    finally:
        job["done"] = True


st.title("Blind Tuner")
question = st.text_input("Question", value="Why is the weekly sales dashboard timing out?")
if st.button("Ask", type="primary"):
    res = data.gateway("/v1/ask/resolve", {"question": question})
    qid = res["question_id"]
    JOBS[qid] = {"done": False, "tids": res["template_ids"]}
    data.start_background(run_job, qid, res["template_ids"])
    st.session_state["qid"] = qid


@st.fragment(run_every="1s")
def result() -> None:
    qid = st.session_state.get("qid")
    if not qid:
        return
    job = JOBS.get(qid, {})
    if "ask" not in job:
        events = data.ai(f"/ai/ask/{qid}/events", method="GET").json()["events"]
        for e in events:
            if e.startswith(("rate limited", "LLM service unavailable")):
                st.warning(e)
        st.info(f"Working: {sum(e.startswith('tool ') for e in events)} tool calls so far")
        return

    status, body = job["ask"]
    st.subheader("Answer")
    if status != 200:
        detail = body.get("detail")
        if isinstance(detail, dict):            # ai's error body: keep its one-line reason only
            detail = detail.get("detail") or detail.get("error") or json.dumps(detail)
        st.error(f"The LLM did not answer: {detail}")
    elif body["status"] != "ok":
        st.error(f"Answer blocked: it held numbers not found in any tool result ({', '.join(body['unmatched'])}).")
    else:
        st.markdown(view(body["answer"]["text"]))
    if not job.get("done"):
        st.info("Measuring on the twin and writing the SQL")
        return
    if job.get("error"):
        st.error(f"Could not measure or write the SQL: {job['error']}")
        return

    sim = job.get("sim")
    if not sim:
        st.info("The search found no change worth its cost, so there is no SQL to apply.")
        return
    st.subheader("Time saved (twin simulation)")
    shown = [t for t in sim["templates"] if t["template_id"] in job["tids"]] or sim["templates"]
    table = next((a["table"] for a in job["config"]["actions"] if a["type"] == "add_index"), None)
    for t in shown:
        saved = t["before_ms"] - t["after_ms"]
        pct = 100 * saved / t["before_ms"] if t["before_ms"] else 0.0
        # Escape $: Streamlit renders text between $ signs as math, which mangled "$1 ... $2".
        label = view(t["template_id"]).replace("$", "\\$") if len(shown) > 1 else "Per run of the query"
        st.metric(label,
                  f"{saved:.1f} ms", f"{pct:.0f}% faster ({t['before_ms']:.1f} to {t['after_ms']:.1f} ms)")
    rows = f"{job['rows'][table]:,}-row " if table in job.get("rows", {}) else ""
    replay = (" Recorded twin measurement, replayed (sandbox.twin_mode: recorded); not re-measured for"
              " this question." if cfg("sandbox.twin_mode") == "recorded" else "")
    st.caption(f"Measured on a synthetic {rows}copy of the data, median of {sim['runs']} runs; not production.{replay}")

    if st.session_state.get("ai_view"):
        st.info("SQL hidden in the AI view: it holds real names.")
        return
    st.subheader("SQL to apply")
    st.code(data.sql_statements(job["files"]["migration.sql"]), language="sql")
    st.subheader("Rollback")
    st.code(data.sql_statements(job["files"]["rollback.sql"]), language="sql")


result()

st.caption(f"Simplified in this build: {data.estimator_label()}; {data.LABELS['search']}; {data.LABELS['twin']}.")

with st.expander("Privacy checks"):
    st.toggle("Show what the AI sees (hashed codes)", key="ai_view")
    led = data.gateway("/v1/ledger")
    c1, c2 = st.columns(2)
    c1.metric("Payloads to the AI side", f"{led['outbound_payloads']:,}")
    c2.metric("Canary hits in them", f"{led['outbound_canary_hits']}")
    if st.button("Run negative control"):
        st.session_state["control"] = data.gateway("/v1/privacy/negative-control", {})
    if "control" in st.session_state:
        st.error(f"With hashing and stripping off, the same logs hold {len(st.session_state['control']['canary_hits'])} "
                 "canary hits (scanned locally, never sent).")
