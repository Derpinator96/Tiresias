"""Gateway API (doc, "Services, APIs and network isolation").

AI-facing endpoints return only hashed contracts, and every one of their responses goes
through Gateway.send_to_ai: validated against its contract, canary-scanned and written to
the ledger before it leaves. A canary hit blocks the response (fail closed, HTTP 403).

Private-side endpoints (dashboard) are not ledgered; /v1/approve refuses the ai container.
"""
from __future__ import annotations

import os
import socket
from functools import lru_cache

from fastapi import Body, FastAPI, HTTPException, Request
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


@app.get("/v1/rewrite/candidates")
def rewrite_candidates():
    """Rules whose shape matches each slow template, with the rewritten hashed SQL."""
    g = gw()
    return _to_ai(None, g.rewrite_candidates(g.snapshot()))


@app.post("/v1/rewrite/verify")
def rewrite_verify(body: dict = Body(...)):
    """{template_id, rule_id} -> Rewrite: VeriEQL on the real SQL plus a twin checksum. The AI
    names a rule; the rewrite itself is applied here, on the private side."""
    g = gw()
    snap = g.snapshot()
    try:
        rw = g.check_rewrite(snap, body["template_id"], body["rule_id"], os.environ["TWIN_DSN"])
    except KeyError:
        raise HTTPException(400, "body needs template_id and rule_id") from None
    except ValueError as e:
        raise HTTPException(409, f"rule does not apply: {e}") from None
    return _to_ai("Rewrite", rw)


@app.post("/v1/twin/checksum")
def twin_checksum(body: dict = Body(...)):
    """{template_id, config} -> {template_id, config_id, match, rows}: does building the
    config's indexes on the twin leave the template's result rows unchanged? Rewrites are
    checked by /v1/rewrite/verify."""
    from db.sandbox import checksum, twin_measure
    config = body.get("config")
    if not isinstance(config, dict):
        raise HTTPException(400, "body needs template_id and config")
    validate("Config", config)
    g = gw()
    snap = g.snapshot()
    tid = body.get("template_id")
    if snap.template(tid) is None:
        raise HTTPException(404, "unknown template")
    try:
        indexes = g.decode_config(config)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"cannot check this config: {type(e).__name__}") from None
    query, generic = g.sample_queries(snap, [tid])[tid]
    if generic:
        raise HTTPException(409, "template has no logged query to replay")
    twin_q = twin_measure.map_query(query, twin_measure.load_map())
    r = checksum.index_preserves_results(os.environ["TWIN_DSN"], indexes, twin_q)
    from gateway.rounding import round_count
    return _to_ai(None, {"template_id": tid, "config_id": config["config_id"], "match": r["match"],
                         "rows": round_count(r["rows"])})


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


def _not_ai(request: Request) -> None:
    """Refuse the ai container on endpoints whose output holds real names and values. Its
    addresses come from Compose's DNS (service `ai`); no answer means ai is not running."""
    try:
        ai_ips = socket.gethostbyname_ex("ai")[2]
    except OSError:
        return
    if request.client and request.client.host in ai_ips:
        raise HTTPException(403, "private-side endpoint: not served to the ai service")


@app.post("/v1/approve")
def approve(request: Request, config: dict = Body(...)):
    """Config -> {config_id, files: {migration.sql, rollback.sql, post_deploy_check.py}} in real
    names, for the operator dashboard. Not ledgered and never sent to ai: the files hold real
    names and logged values. Runs nothing on pg-prod; the DBA runs the files. The doc's table
    says `config_id` in; the gateway keeps no config store, so the dashboard sends the Config."""
    from gateway import approve as approve_mod
    _not_ai(request)
    validate("Config", config)
    g = gw()
    try:
        files = approve_mod.build(g, g.snapshot(), config)
    except KeyError as e:
        raise HTTPException(400, f"cannot approve this config: unknown code {e}") from None
    except ValueError as e:
        raise HTTPException(400, f"cannot approve this config: {e}") from None
    return JSONResponse({"config_id": config["config_id"], "files": files})


@app.post("/v1/approve/twin-check")
def approve_twin_check(request: Request, config: dict = Body(...)):
    """Demo: run the approve files on pg-twin (never pg-prod) with a shortened replay; the twin
    is returned to its baseline afterwards. See gateway.approve.twin_check."""
    import subprocess

    import psycopg

    from gateway import approve as approve_mod
    _not_ai(request)
    validate("Config", config)
    g = gw()
    try:
        return JSONResponse(approve_mod.twin_check(g, g.snapshot(), config, os.environ["TWIN_DSN"]))
    except KeyError as e:
        raise HTTPException(400, f"cannot check this config: unknown code {e}") from None
    except ValueError as e:
        raise HTTPException(400, f"cannot check this config: {e}") from None
    except subprocess.CalledProcessError as e:
        raise HTTPException(409, f"post-deploy check failed on the twin: {e.stderr.strip().splitlines()[-1:]}") from None
    except psycopg.Error as e:
        raise HTTPException(409, f"migration or rollback failed on the twin: {e}") from None
