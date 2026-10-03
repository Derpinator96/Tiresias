"""AI service API (boundary side; hashed data only). Endpoints are added step by step:
/ai/mine (step 7), /ai/gnn/predict (step 8), /ai/rl/run (step 9), /ai/ask (step 11)."""
from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException

from agent import gateway_client as gw
from contracts.validate import validate
from miner import fpgrowth
from models.gnn import predictor as pred

app = FastAPI(title="Blind Tuner ai", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


def existing_indexes(column_meta: list[dict]) -> list[tuple[str, list[str]]]:
    """SIMPLIFIED: ColumnMeta says only whether a column is indexed, not which composite index
    it belongs to, so each primary key column is treated as a one-column index."""
    return [(c["table"], [c["col"]]) for c in column_meta if c["bits"]["pk"]]


def mine() -> dict:
    templates = gw.get("/v1/templates/slow")
    meta = gw.get("/v1/meta/columns")
    return {"candidates": fpgrowth.candidates(templates, meta, existing_indexes(meta)),
            "drift": {"state": "MISSING", "note": "drift detection is not built yet"}}


@app.post("/ai/mine")
def ai_mine() -> dict:
    return mine()


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
    return {"status": r.status, "answer": r.answer, "unmatched": r.unmatched,
            "tool_calls": r.tool_calls, "events": r.events}


@app.get("/ai/ask/{question_id}/events")
def ai_ask_events(question_id: str) -> dict:
    return {"question_id": question_id, "events": EVENTS.get(question_id, [])}


@app.post("/ai/rl/run")
def ai_rl_run(body: dict | None = Body(None)) -> dict:
    """Template weights (optional; default share of calls) -> best Config with each action's
    contribution, plus the search trace."""
    from rl import search
    config, trace = search.run((body or {}).get("weights"))
    validate("Config", config)
    return {"config": config, "label": search.LABEL, "estimator_label": pred.load_predictor().label,
            "baseline_predicted_ms": round(trace.baseline_ms, 3), "final_predicted_ms": round(trace.final_ms, 3),
            "steps": trace.steps, "configs_costed": trace.evaluated, "cache_hits": trace.cache_hits,
            "episodes": trace.episodes, "top_configs": trace.top_configs, "greedy": trace.greedy}


@app.get("/ai/gnn/estimator")
def ai_gnn_estimator() -> dict:
    """Which runtime estimator is serving, so every on-screen label names the real one."""
    model = pred.load_predictor()
    return {"estimator": model.estimator, "label": model.label}


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
