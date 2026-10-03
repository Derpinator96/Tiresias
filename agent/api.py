"""AI service API. PLACEHOLDER: only /healthz exists; steps 7 to 11 add /ai/* endpoints."""
from fastapi import FastAPI

app = FastAPI(title="Blind Tuner ai", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "status": "PLACEHOLDER: endpoints arrive in steps 7 to 11"}
