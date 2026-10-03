"""Gateway API (doc, "Services, APIs and network isolation").

AI-facing endpoints return only hashed contracts, and every one of their responses goes
through Gateway.send_to_ai: validated against its contract, canary-scanned and written to
the ledger before it leaves. A canary hit blocks the response (fail closed, HTTP 403).

Endpoints that later build steps implement return 501 with the step that adds them.
"""
from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response

from common.config import cfg
from contracts.validate import validate
from gateway.service import Blocked, Gateway

app = FastAPI(title="Blind Tuner gateway", docs_url=None, redoc_url=None, openapi_url=None)


@lru_cache(maxsize=1)
def gw() -> Gateway:
    return Gateway(os.environ["PROD_DSN"], os.environ["PGLOG_DIR"])


def _to_ai(contract: str | None, payload) -> Response:
    try:
        return Response(gw().send_to_ai(contract, payload), media_type="application/json")
    except Blocked as b:
        raise HTTPException(403, {"blocked": True, "payload_id": b.entry["payload_id"],
                                  "canary_hits": b.entry["canary_hits"]}) from None


def _pending(step: int, what: str):
    raise HTTPException(501, f"{what}: not built yet (build step {step})")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ---- AI-facing (boundary) ---------------------------------------------------------------
@app.get("/v1/templates/slow")
def templates_slow():
    g = gw()
    return _to_ai("HashedQuery", g.slow_templates(g.snapshot()))


@app.get("/v1/templates/{template_id}/plans")
def template_plans(template_id: str):
    g = gw()
    snap = g.snapshot()
    if snap.template(template_id) is None:
        raise HTTPException(404, "unknown template")
    return _to_ai("HashedPlan", g.hashed_plans(snap, template_id))


@app.get("/v1/meta/columns")
def meta_columns():
    g = gw()
    return _to_ai("ColumnMeta", g.column_meta(g.snapshot()))


@app.get("/v1/meta/tables")
def meta_tables():
    g = gw()
    return _to_ai("TableMeta", g.table_meta(g.snapshot()))


@app.post("/v1/simulate/hypopg")
def simulate_hypopg(config: dict = Body(...)):
    """Config -> {plans: HashedPlan[] (estimated), index_storage_mb}. The size comes from
    hypopg_relation_size; the doc's table lists only the plans, the size is added so the
    search can apply its storage penalty without a second round trip."""
    validate("Config", config)
    g = gw()
    snap = g.snapshot()
    try:
        out = g.simulate_hypopg(snap, config)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"cannot simulate this config: {type(e).__name__}") from None
    for p in out["plans"]:
        validate("HashedPlan", p)
    return _to_ai(None, out)


@app.post("/v1/simulate/twin")
def simulate_twin(config: dict = Body(...)):
    """Config -> SimResult measured on pg-twin. If the twin's plan shape for any template
    differs from production's, no number is returned (doc: plan agreement before trust)."""
    validate("Config", config)
    g = gw()
    snap = g.snapshot()
    try:
        sim, agreement = g.simulate_twin(snap, config, os.environ["TWIN_DSN"])
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"cannot simulate this config: {type(e).__name__}") from None
    disagree = sorted(tid for tid, ok in agreement.items() if not ok)
    if disagree:
        raise HTTPException(409, {"plan_disagreement": disagree})
    validate("SimResult", sim)
    return _to_ai("SimResult", sim)


@app.post("/v1/twin/checksum")
def twin_checksum(body: dict = Body(...)):
    _pending(12, "twin checksum")


@app.post("/v1/ledger/outbound")
def ledger_outbound(payload: dict = Body(...)):
    """ai submits each LLM request body here first and sends it only on verdict allow."""
    validate("OutboundPayload", payload)
    return gw().check_outbound(payload["body"])


# ---- private side (dashboard) ----------------------------------------------------------
@app.post("/v1/ask/resolve")
def ask_resolve(body: dict = Body(...)):
    g = gw()
    return g.resolve(str(body.get("question", "")), g.snapshot())


@app.post("/v1/answers/dehash")
def answers_dehash(answer: dict = Body(...)):
    validate("Answer", answer)
    g = gw()
    return {"question_id": answer["question_id"], "text": g.dehash(answer["text"], g.snapshot())}


@app.get("/v1/ledger")
def ledger():
    entries = gw().ledger.entries()
    outbound = [e for e in entries if e["destination"] in ("ai", "llm")]
    control = [e for e in entries if e["destination"] == "local_scanner"]
    return JSONResponse({
        "entries": entries,
        # Payloads bound for the AI side or the LLM: the "N payloads, 0 canaries" counter.
        "outbound_payloads": len(outbound),
        "outbound_canary_hits": sum(len(e["canary_hits"]) for e in outbound),
        "outbound_blocked": sum(e["verdict"] == "block" for e in outbound),
        # Negative-control scans: local only, never sent anywhere.
        "control_runs": len(control),
        "control_canary_hits": sum(len(e["canary_hits"]) for e in control),
        "canaries_planted": int(cfg("canaries.planted_target")),
    })


@app.post("/v1/privacy/negative-control")
def negative_control():
    return gw().negative_control()


@app.post("/v1/approve")
def approve():
    raise HTTPException(501, "approve and migration scripts: out of scope this session")
