"""HTTP client for the gateway, used on the AI side. Everything it returns is hashed."""
from __future__ import annotations

import os

import httpx

TIMEOUT_S = 120.0


def _url(path: str) -> str:
    return os.environ["GATEWAY_URL"].rstrip("/") + path


def get(path: str):
    r = httpx.get(_url(path), timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def post(path: str, body, timeout: float = TIMEOUT_S):
    r = httpx.post(_url(path), json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()
