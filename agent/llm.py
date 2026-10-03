"""LLM provider adapter (decision C). Provider and model come from config.yaml.

Gemini is called through its REST API (generateContent), not the SDK, so the exact request
bytes are known: every body is first sent to the gateway's POST /v1/ledger/outbound, which
scans and ledgers it, and is sent to the LLM only on verdict "allow" (fail closed).

Request and response shapes checked on 2026-10-03 against
https://ai.google.dev/api/generate-content (GenerateContentRequest: contents,
systemInstruction, tools[].functionDeclarations, toolConfig.functionCallingConfig.mode,
generationConfig.temperature; Part: text, functionCall {id, name, args},
functionResponse {id, name, response}, thoughtSignature). The model's own turn is sent back
unchanged so any thoughtSignature parts are returned as the API expects.
Not yet exercised against the live API: GEMINI_API_KEY was not set when this was written.

HTTP 429 is retried with exponential backoff (llm.retry_* in config.yaml), honouring a
Retry-After header when present. Each retry is reported through on_event, which the
dashboard shows as "rate limited, retrying".
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

import httpx

from agent import gateway_client as gw
from common.config import cfg

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class MissingKey(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


class OutboundBlocked(RuntimeError):
    def __init__(self, entry: dict):
        super().__init__("LLM request blocked by the gateway's canary scan")
        self.entry = entry


class GeminiREST:
    def __init__(self, model: str, api_key: str, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self._key = api_key
        self._client = httpx.Client(transport=transport, timeout=120.0)
        self._sleep = sleep

    def generate(self, system: str, contents: list[dict], declarations: list[dict],
                 on_event: Callable[[str], None] = lambda _: None) -> dict:
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": declarations}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {"temperature": cfg("llm.temperature")},
        })
        entry = gw.post("/v1/ledger/outbound", {"destination": "llm", "body": body})
        if entry["verdict"] != "allow":
            raise OutboundBlocked(entry)

        attempts = int(cfg("llm.retry_max_attempts"))
        delay = float(cfg("llm.retry_initial_backoff_s"))
        for attempt in range(1, attempts + 1):
            r = self._client.post(GEMINI_URL.format(model=self.model), content=body.encode("utf-8"),
                                  headers={"Content-Type": "application/json", "x-goog-api-key": self._key})
            if r.status_code != 429:
                r.raise_for_status()
                return r.json()
            if attempt == attempts:
                break
            retry_after = r.headers.get("Retry-After")
            wait = min(float(retry_after) if retry_after and retry_after.isdigit() else delay,
                       float(cfg("llm.retry_max_backoff_s")))
            on_event(f"rate limited, retrying in {wait:.0f} s (attempt {attempt + 1} of {attempts})")
            self._sleep(wait)
            delay *= float(cfg("llm.retry_backoff_multiplier"))
        on_event(f"rate limited, gave up after {attempts} attempts")
        raise RateLimited(f"LLM API returned 429 on all {attempts} attempts")


def provider(transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep):
    """The configured provider. The key is read from the env var named in config.yaml."""
    name = cfg("llm.provider")
    key = os.environ.get(cfg("llm.api_key_env"), "")
    if not key:
        raise MissingKey(f"{cfg('llm.api_key_env')} is not set")
    if name == "gemini":
        return GeminiREST(cfg("llm.model"), key, transport, sleep)
    raise ValueError(f"unknown llm.provider {name!r}")
