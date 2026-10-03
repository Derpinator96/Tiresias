"""Gateway API. PLACEHOLDER: only /healthz exists; step 6 adds the Q1 endpoints."""
from fastapi import FastAPI

app = FastAPI(title="Blind Tuner gateway", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "status": "PLACEHOLDER: endpoints arrive in step 6"}
