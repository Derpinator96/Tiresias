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


def calibrated_predictor(plans: list[dict]) -> pred.CostPredictor:
    """Calibrate on measured plans in the request, else on the gateway's measured
    auto_explain plans for the same templates."""
    measured = [p for p in plans if p["source"] == "auto_explain"]
    if not measured:
        for tid in sorted({p["template_id"] for p in plans}):
            measured += gw.get(f"/v1/templates/{tid}/plans")
    return pred.CostPredictor().fit(measured)


def predict_plans(plans: list[dict]) -> list[dict]:
    for p in plans:
        validate("HashedPlan", p)
    model = calibrated_predictor(plans)
    out = [pred.predict(p, model) for p in plans]
    for o in out:
        validate("Prediction", o)
    return out


@app.post("/ai/rl/run")
def ai_rl_run(body: dict | None = Body(None)) -> dict:
    """Template weights (optional; default share of calls) -> best Config with each action's
    contribution, plus the search trace."""
    from rl import search
    config, trace = search.run((body or {}).get("weights"))
    validate("Config", config)
    return {"config": config, "label": search.LABEL, "estimator_label": pred.LABEL,
            "baseline_predicted_ms": round(trace.baseline_ms, 3), "final_predicted_ms": round(trace.final_ms, 3),
            "steps": trace.steps, "configs_costed": trace.evaluated, "cache_hits": trace.cache_hits}


@app.post("/ai/gnn/predict")
def ai_gnn_predict(plans: list[dict] = Body(...)) -> list[dict]:
    try:
        return predict_plans(plans)
    except pred.NotCalibrated as e:
        raise HTTPException(409, str(e)) from None
