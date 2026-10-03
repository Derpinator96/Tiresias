"""AI service API (boundary side; hashed data only). Endpoints are added step by step:
/ai/mine (step 7), /ai/gnn/predict (step 8), /ai/rl/run (step 9), /ai/ask (step 11)."""
from __future__ import annotations

from fastapi import FastAPI

from agent import gateway_client as gw
from miner import fpgrowth

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
