"""AI service API (boundary side; hashed data only). Endpoints are added step by step:
/ai/mine (step 7), /ai/gnn/predict (step 8), /ai/rl/run (step 9), /ai/ask (step 11)."""
from __future__ import annotations

import httpx
from fastapi import Body, FastAPI, HTTPException

from agent import gateway_client as gw
from common.config import cfg
from contracts.validate import validate
from miner import drift, fpgrowth
from models.gnn import predictor as pred

app = FastAPI(title="Blind Tuner ai", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


COVERED_LABEL = "miner: covered-index check knows primary keys only"


def existing_indexes(column_meta: list[dict]) -> list[tuple[str, list[str]]]:
    """SIMPLIFIED: ColumnMeta says only whether a column is indexed, not which composite index
    it belongs to, so each primary key column is treated as a one-column index."""
    return [(c["table"], [c["col"]]) for c in column_meta if c["bits"]["pk"]]


def mine(window_s: int | None = None) -> dict:
    """Candidates plus the drift state. window_s overrides the configured drift window (tests)."""
    templates = fpgrowth.with_rewritten_shapes(gw.get("/v1/templates/slow"), gw.get("/v1/rewrite/candidates"))
    meta = gw.get("/v1/meta/columns")
    win = gw.get("/v1/workload/windows" + (f"?window_s={int(window_s)}" if window_s else ""))
    return {"candidates": fpgrowth.candidates(templates, meta, existing_indexes(meta)),
            "label": COVERED_LABEL, "drift": drift.state(win["windows"], win["window_s"])}


@app.post("/ai/mine")
def ai_mine(body: dict | None = Body(None)) -> dict:
    return mine((body or {}).get("window_s"))


def calibrated_predictor(plans: list[dict]):
    """The serving predictor (pred.load_predictor). The calibrated baseline is calibrated on
    measured plans in the request, else on the gateway's measured auto_explain plans for the
    same templates; the GNN needs no calibration."""
    model = pred.load_predictor()
    if not model.needs_calibration:
        return model
    measured = [p for p in plans if p["source"] == "auto_explain"]
    if not measured:
        for tid in sorted({p["template_id"] for p in plans}):
            measured += gw.get(f"/v1/templates/{tid}/plans")
    return model.fit(measured)


def predict_plans(plans: list[dict]) -> list[dict]:
    for p in plans:
        validate("HashedPlan", p)
    model = calibrated_predictor(plans)
    out = [pred.predict(p, model) for p in plans]
    for o in out:
        validate("Prediction", o)
    return out


EVENTS: dict[str, list[str]] = {}     # question_id -> progress events, polled by the dashboard


@app.post("/ai/ask")
def ai_ask(body: dict = Body(...)) -> dict:
    """{question_id, template_ids} -> {status, answer (contract Answer, hashed), tool_calls, events}.
    The DBA's question text is never received here; the gateway resolved it privately."""
    from agent import agent as agent_mod
    from agent import llm
    qid, tids = body["question_id"], list(body.get("template_ids", []))
    EVENTS[qid] = []
    try:
        provider = llm.provider()
    except llm.MissingKey as e:
        raise HTTPException(503, str(e)) from None
    try:
        r = agent_mod.ask(qid, tids, provider, on_event=EVENTS[qid].append)
    except llm.RateLimited as e:
        raise HTTPException(503, {"error": "rate limited", "detail": str(e), "events": EVENTS[qid]}) from None
    except llm.OutboundBlocked as e:
        raise HTTPException(403, {"error": "LLM request blocked by canary scan", "payload_id": e.entry["payload_id"]}) from None
    except (llm.ContextOverflow, llm.MalformedReply, httpx.TransportError) as e:
        raise HTTPException(503, {"error": type(e).__name__, "detail": str(e), "events": EVENTS[qid]}) from None
    except httpx.HTTPStatusError as e:   # e.g. Ollama 404 when the model is not pulled
        raise HTTPException(502, {"error": "LLM HTTP error", "detail": f"{e.response.status_code}: {e.response.text[:300]}",
                                  "events": EVENTS[qid]}) from None
    return {"status": r.status, "answer": r.answer, "unmatched": r.unmatched,
            "tool_calls": r.tool_calls, "events": r.events}


@app.get("/ai/llm")
def ai_llm() -> dict:
    """Which LLM answers /ai/ask, so the dashboard names it (and, for the local model, whether
    ai can still reach the LLM API host)."""
    from agent import llm
    name, label = llm.provider_name(), llm.label()
    return {"provider": name, "model": cfg("llm.ollama.model") if name == "ollama" else cfg("llm.model"),
            "label": label, "air_gapped": label.endswith(llm.ROUTE_NONE)}


@app.get("/ai/ask/{question_id}/events")
def ai_ask_events(question_id: str) -> dict:
    return {"question_id": question_id, "events": EVENTS.get(question_id, [])}


@app.post("/ai/rl/run")
def ai_rl_run(body: dict | None = Body(None)) -> dict:
    """Template weights (optional; default share of calls) -> best Config with each action's
    contribution, plus the search trace. top_configs holds every configuration re-checked on
    the twin (predicted, raw HypoPG and measured numbers, and which one was chosen); rewrites
    holds the check status of every matching rewrite."""
    from rl import search
    config, trace = search.run((body or {}).get("weights"))
    validate("Config", config)
    return {"config": config, "label": search.LABEL, "estimator_label": pred.load_predictor().label,
            "baseline_predicted_ms": round(trace.baseline_ms, 3), "final_predicted_ms": round(trace.final_ms, 3),
            "steps": trace.steps, "configs_costed": trace.evaluated, "cache_hits": trace.cache_hits,
            "episodes": trace.episodes, "top_configs": trace.top_configs, "greedy": trace.greedy,
            "rewrites": trace.rewrites, "final_choice": trace.final_choice,
            "q_entries": len(search._Q)}   # the Q-table persists in this process across runs


@app.get("/ai/gnn/estimator")
def ai_gnn_estimator() -> dict:
    """Which runtime estimator is serving, so every on-screen label names the real one."""
    model = pred.load_predictor()
    return {"estimator": model.estimator, "label": model.label}


@app.post("/ai/gnn/explain")
def ai_gnn_explain(body: dict = Body(...)) -> dict:
    """{template_id} -> the LLM tool gnn_explain's result (agent/tools.py): the latest plan's
    nodes with the largest predicted share, row misestimates and the ANALYZE tip, labelled with
    the serving estimator. The dashboard shows it as each recommendation's reason."""
    from agent.tools import Toolbox
    if "template_id" not in body:
        raise HTTPException(400, "body needs template_id")
    try:
        out = Toolbox().gnn_explain(body["template_id"])
    except httpx.HTTPStatusError as e:      # the gateway's 404 for an unknown template
        raise HTTPException(e.response.status_code, e.response.text[:300]) from None
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@app.post("/ai/gnn/predict")
def ai_gnn_predict(plans: list[dict] = Body(...)) -> list[dict]:
    try:
        return predict_plans(plans)
    except pred.NotCalibrated as e:
        raise HTTPException(409, str(e)) from None


@app.post("/ai/privacy/adversary")
def ai_privacy_adversary(body: dict = Body(...)) -> dict:
    """{since, until} (ISO times with a timezone) -> the adversarial LLM's guess per code for the
    payloads of that window (agent/adversary.py). Scored on the private side."""
    from urllib.parse import urlencode

    from agent import adversary, llm
    if not {"since", "until"} <= body.keys():
        raise HTTPException(400, "body needs since and until")
    try:
        material = gw.get("/v1/ledger/payloads?" + urlencode({"since": body["since"], "until": body["until"]}))
        return adversary.run(material["payloads"], llm.provider())
    except llm.MissingKey as e:
        raise HTTPException(503, str(e)) from None
    except llm.RateLimited as e:
        raise HTTPException(503, {"error": "rate limited", "detail": str(e)}) from None
    except llm.OutboundBlocked as e:
        raise HTTPException(403, {"error": "LLM request blocked by canary scan", "payload_id": e.entry["payload_id"]}) from None
