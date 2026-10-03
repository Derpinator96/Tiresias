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
    """{question_id, template_ids} -> {status, answer (contract Answer, hashed), tool_calls, events,
    config, simulation}. config and simulation are the Config from the agent's last run_rl call
    and the twin SimResult (plus speedup_pct) from its last simulate call, or null if it made
    no such call; the dashboard shows them next to the answer.
    The DBA's question text is never received here; the gateway resolved it privately.

    Optional, for make llm-bench and the per-provider e2e test (production switches provider in
    config.yaml only): "llm": {"provider": gemini|nim|ollama, "model": ...} overrides the
    configured provider for this request; "record": true returns every LLM exchange and tool
    call in "record" (agent/recording.py). The reply also carries seconds, the provider and
    model used, and the provider's tool-call errors.

    Fallback (llm.fallback, human decision 2026-10-03): when a provider fails with one of
    llm.FAILOVER_ERRORS, the whole question is asked again of the next provider in llm.chain(),
    with the same toolbox (its cached results are reused; every new LLM body is scanned again).
    "failovers" lists each provider that failed and why. A canary block is never failed over."""
    import time as _time

    from agent import agent as agent_mod
    from agent import llm
    from agent.recording import RecordingToolbox, RecordingTransport
    from agent.tools import Toolbox
    qid, tids = body["question_id"], list(body.get("template_ids", []))
    choice = body.get("llm") or {}
    if choice.get("provider") not in (None, *llm.PROVIDERS):
        raise HTTPException(400, f"unknown provider {choice.get('provider')!r}")
    record = bool(body.get("record"))
    EVENTS[qid] = []
    transport = RecordingTransport() if record else None
    toolbox = RecordingToolbox() if record else Toolbox()
    started = _time.monotonic()
    names, failovers = llm.chain(choice.get("provider")), []
    try:
        for i, name in enumerate(names):
            try:
                provider = llm.provider(transport, name=name, model=choice.get("model"))
                r = agent_mod.ask(qid, tids, provider, toolbox=toolbox, on_event=EVENTS[qid].append)
                break
            except llm.FAILOVER_ERRORS as e:
                if i == len(names) - 1:
                    raise
                failovers.append({"provider": name, "error": f"{type(e).__name__}: {str(e)[:200]}"})
                EVENTS[qid].append(f"{name} failed ({type(e).__name__}), asking {names[i + 1]} instead")
    except llm.MissingKey as e:
        raise HTTPException(503, {"error": "no LLM provider available", "detail": str(e), "failovers": failovers}) from None
    except llm.RateLimited as e:
        raise HTTPException(503, {"error": "rate limited", "detail": str(e), "events": EVENTS[qid]}) from None
    except llm.OutboundBlocked as e:
        raise HTTPException(403, {"error": "LLM request blocked by canary scan", "payload_id": e.entry["payload_id"]}) from None
    except (llm.ContextOverflow, llm.MalformedReply, httpx.TransportError) as e:
        raise HTTPException(503, {"error": type(e).__name__, "detail": str(e), "events": EVENTS[qid]}) from None
    except httpx.HTTPStatusError as e:   # e.g. Ollama 404 when the model is not pulled
        raise HTTPException(502, {"error": "LLM HTTP error", "detail": f"{e.response.status_code}: {e.response.text[:300]}",
                                  "events": EVENTS[qid]}) from None
    out = {"status": r.status, "answer": r.answer, "unmatched": r.unmatched,
           "tool_calls": r.tool_calls, "events": r.events,
           "config": toolbox.last_config, "simulation": toolbox.last_simulation,
           "seconds": round(_time.monotonic() - started, 2),
           "llm": {"provider": name, "model": provider.model}, "failovers": failovers,
           "tool_call_errors": list(getattr(provider, "tool_call_errors", []))}
    if record:
        out["record"] = {"exchanges": transport.exchanges, "tool_calls": toolbox.recorded}
    return out


@app.post("/ai/llm/probe")
def ai_llm_probe(body: dict = Body(...)) -> dict:
    """{provider, model} -> does the model return a tool call for one synthetic request? The
    request holds no data (a fixed instruction and one tool with no arguments) and goes through
    the outbound scan like every LLM body. Used by make llm-bench to find candidates whose
    hosted deployment has tool calling enabled; the model list does not say."""
    import time as _time

    from agent import llm
    name, model = body.get("provider", "nim"), body.get("model")
    if name not in llm.PROVIDERS or not model:
        raise HTTPException(400, "provider and model are required")
    decl = [{"name": "get_slow_templates", "description": "Top query templates by total time.",
             "parameters": {"type": "object", "properties": {}}}]
    started = _time.monotonic()
    events: list[str] = []          # retry events: each one is a 429 or 5xx the API returned
    try:
        p = llm.provider(name=name, model=model)
        out = p.generate("You are a test. Call the tool get_slow_templates now; do not answer in text.",
                         [{"role": "user", "parts": [{"text": "Call get_slow_templates."}]}], decl, on_event=events.append)
    except llm.MissingKey as e:
        raise HTTPException(503, str(e)) from None
    except (llm.RateLimited, llm.MalformedReply, httpx.HTTPError) as e:
        detail = f"{e.response.status_code}: {e.response.text[:200]}" if isinstance(e, httpx.HTTPStatusError) else str(e)
        return {"model": model, "tool_call": False, "error": f"{type(e).__name__}: {detail}", "events": events,
                "seconds": round(_time.monotonic() - started, 2)}
    parts = out["candidates"][0]["content"]["parts"]
    called = [pt["functionCall"]["name"] for pt in parts if "functionCall" in pt]
    return {"model": model, "tool_call": called == ["get_slow_templates"], "called": called,
            "text": "".join(pt.get("text", "") for pt in parts)[:200],
            "tool_call_errors": list(getattr(p, "tool_call_errors", [])), "events": events,
            "seconds": round(_time.monotonic() - started, 2)}


@app.get("/ai/llm/models")
def ai_llm_models(provider: str = "nim") -> dict:
    """Model IDs the hosted provider lists (GET {base_url}/models; no request body, so nothing
    to ledger). NIM only: Gemini's model is checked by agent/tests/test_live_llm.py."""
    from agent import llm
    if provider != "nim":
        raise HTTPException(400, "only provider nim lists models here")
    try:
        p = llm.provider(name="nim", model="list-only")
        return {"provider": "nim", "models": p.list_models()}
    except llm.MissingKey as e:
        raise HTTPException(503, str(e)) from None
    except httpx.HTTPError as e:
        raise HTTPException(502, f"model list failed: {type(e).__name__}") from None


@app.get("/ai/llm")
def ai_llm() -> dict:
    """Which LLM answers /ai/ask, so the dashboard names it (and, for the local model, whether
    ai can still reach the LLM API host)."""
    from agent import llm
    name, label = llm.provider_name(), llm.label()
    model = cfg("llm.model") if name == "gemini" else cfg(f"llm.{name}.model")
    return {"provider": name, "model": model, "fallback": llm.chain()[1:],
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
        names = llm.chain()
        for i, name in enumerate(names):
            try:
                return adversary.run(material["payloads"], llm.provider(name=name))
            except llm.FAILOVER_ERRORS:
                if i == len(names) - 1:
                    raise
    except llm.MissingKey as e:
        raise HTTPException(503, str(e)) from None
    except llm.RateLimited as e:
        raise HTTPException(503, {"error": "rate limited", "detail": str(e)}) from None
    except llm.OutboundBlocked as e:
        raise HTTPException(403, {"error": "LLM request blocked by canary scan", "payload_id": e.entry["payload_id"]}) from None
