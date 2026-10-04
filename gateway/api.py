"""Gateway API (doc, "Services, APIs and network isolation").

AI-facing endpoints return only hashed contracts, and every one of their responses goes
through Gateway.send_to_ai: validated against its contract, canary-scanned and written to
the ledger before it leaves. A canary hit blocks the response (fail closed, HTTP 403).

Private-side endpoints (dashboard) are not ledgered; /v1/approve refuses the ai container.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from common.config import cfg
from contracts.validate import validate
from gateway import windows as windows_mod
from gateway.service import Blocked, Gateway


@asynccontextmanager
async def lifespan(_app):
    gw()                     # the real gateway starts sampling drift windows at boot
    yield

app = FastAPI(title="Blind Tuner gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@lru_cache(maxsize=1)
def gw() -> Gateway:
    g = Gateway(os.environ["PROD_DSN"], os.environ["PGLOG_DIR"])
    g.windows.start()
    return g


def _to_ai(contract: str | None, payload, keep_body: bool = True) -> Response:
    try:
        return Response(gw().send_to_ai(contract, payload, keep_body), media_type="application/json")
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


@app.get("/v1/workload/windows")
def workload_windows(window_s: int | None = None):
    """-> {window_s, windows: [{end, templates: {template_id: {time_share, call_share}}}]}, closed
    windows oldest first. Shares only. window_s defaults to the configured drift window; a
    shorter one is a test-only parameter, the configured value is what the demo uses."""
    w = windows_mod.window_s() if window_s is None else window_s
    if w <= 0:
        raise HTTPException(400, "window_s must be positive")
    return _to_ai(None, {"window_s": w, "windows": gw().windows.windows(w)})


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
    key = _twin_record_key(config, [t["template_id"] for t in g.slow_templates(snap)])
    if cfg("sandbox.twin_mode") == "recorded":
        rec = _twin_records().get(key)
        if rec is not None:
            return _to_ai("SimResult", {**rec["sim"], "config_id": config["config_id"]})
        # Never touches the twin in this mode: an unrecorded config is estimated from HypoPG
        # costs (human decision 2026-10-04); the estimate is not saved as a record.
        try:
            sim = g.estimate_twin(snap, config)
        except (KeyError, ValueError) as e:
            raise HTTPException(400, f"cannot estimate this config: {type(e).__name__}") from None
        validate("SimResult", sim)
        return _to_ai("SimResult", sim)
    try:
        sim, agreement = g.simulate_twin(snap, config, os.environ["TWIN_DSN"])
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"cannot simulate this config: {type(e).__name__}") from None
    disagree = sorted(tid for tid, ok in agreement.items() if not ok)
    if disagree:
        raise HTTPException(409, {"plan_disagreement": disagree})
    validate("SimResult", sim)
    _save_twin_record(key, sim)
    return _to_ai("SimResult", sim)


# Recorded twin measurements (human decision 2026-10-04, sandbox.twin_mode). Every live twin
# measurement is saved here, keyed by the config's actions and the slow-template set; in
# "recorded" mode the twin is never used: a recorded config is answered from this file, any
# other config is estimated from HypoPG costs (Gateway.estimate_twin, human decision 2026-10-04).
# The recorded numbers are real twin measurements, replayed; the dashboard labels them as recorded.
_TWIN_LOCK = threading.Lock()


def _twin_record_key(config: dict, template_ids: list[str]) -> str:
    """What the config does, not how it was found: an action's contribution (the search's
    predicted saving) and cand_id (the miner's label) differ between the search and the
    dashboard for the same action, so both are left out."""
    actions = [{k: v for k, v in a.items() if k not in ("contribution", "cand_id")} for a in config["actions"]]
    return json.dumps({"actions": sorted(json.dumps(a, sort_keys=True) for a in actions),
                       "templates": sorted(template_ids)}, sort_keys=True)


def _twin_records() -> dict:
    path = Path(cfg("sandbox.twin_record_path"))
    with _TWIN_LOCK:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_twin_record(key: str, sim: dict) -> None:
    path = Path(cfg("sandbox.twin_record_path"))
    with _TWIN_LOCK:
        records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        records[key] = {"sim": sim, "recorded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=1), encoding="utf-8")
        tmp.replace(path)


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


@app.get("/v1/ledger/payloads")
def ledger_payloads(since: str, until: str):
    """Payloads already sent to the AI side or the LLM between two ISO times with a timezone,
    one copy each: the input of the adversarial leak test (privacy_tests/). Leaves through
    send_to_ai like every AI-facing response; its own bytes are not kept, so a later window
    never contains this bundle."""
    try:
        lo, hi = datetime.fromisoformat(since), datetime.fromisoformat(until)
    except ValueError:
        raise HTTPException(400, "since and until must be ISO times") from None
    if lo.tzinfo is None or hi.tzinfo is None:
        raise HTTPException(400, "since and until need a timezone")
    return _to_ai(None, {"payloads": gw().ledger.payloads(lo, hi)}, keep_body=False)


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


@app.get("/v1/withheld")
def withheld(request: Request):
    """Statements withheld because the gateway could not parse them ("unparsed, not sent"):
    queryid, reason and first-seen time only, never the text. Private side."""
    _not_ai(request)
    return JSONResponse(sorted(gw().withheld.values(), key=lambda w: w["first_seen"]))


# ---- private side (local web app: real names and values, refused to ai) -------------------
@app.get("/v1/private/names")
def private_names(request: Request):
    """{code: real}: t_ table, c_ table.column, i_ index, q_ normalized SQL."""
    _not_ai(request)
    g = gw()
    return JSONResponse(g.real_names(g.snapshot()))


@app.get("/v1/private/slow-log")
def private_slow_log(request: Request):
    """Every template with real SQL, raw calls and times, slow flag and its latest logged
    literal query (or null), total_ms descending."""
    _not_ai(request)
    g = gw()
    return JSONResponse(g.slow_log(g.snapshot()))


@app.get("/v1/private/slow-log/random")
def private_slow_log_random(request: Request):
    import random
    _not_ai(request)
    g = gw()
    rows = g.slow_log(g.snapshot())["templates"]
    if not rows:
        raise HTTPException(404, "no templates yet")
    return JSONResponse(random.choice(rows))


@app.get("/v1/private/tables")
def private_tables(request: Request, rows: int | None = None):
    """Every table: code, row estimate, size, columns with codes and `rows` sample rows."""
    _not_ai(request)
    n = int(cfg("web.sample_rows")) if rows is None else rows
    n = max(0, min(n, int(cfg("web.sample_rows_max"))))
    g = gw()
    return JSONResponse(g.tables(g.snapshot(), n))


@app.post("/v1/private/query")
def private_query(request: Request, body: dict = Body(...)):
    """{sql} -> {sql, columns, rows, truncated, ms}: one read-only SELECT on pg-prod for the
    local web app's data questions (gateway/private_query.py). Rows stay on the private side."""
    from gateway import private_query as pq
    _not_ai(request)
    if not isinstance(body.get("sql"), str) or not body["sql"].strip():
        raise HTTPException(400, "sql is required")
    try:
        return pq.run(gw().prod_dsn, body["sql"])
    except pq.Rejected as e:
        raise HTTPException(400, str(e)) from None


@app.get("/v1/twin/fidelity")
def twin_fidelity():
    """The last `make fidelity` result (db/sandbox/fidelity.py), or null before the first run.
    For the dashboard; the file holds query IDs and timings, no table or column name."""
    try:
        with open(cfg("sandbox.fidelity_path"), encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except FileNotFoundError:
        return None


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
