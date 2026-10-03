"""Record one live agent run so tests can replay it without the network (make llm-bench).

RecordingTransport sits under a provider's httpx client and keeps every exchange: URL (no
query string), request body, status and response body. Headers are not kept, so the API key
never reaches a fixture. ReplayTransport returns recorded responses in order.
RecordingToolbox keeps every tool call (ID, name, arguments, result); ReplayToolbox hands the
same IDs and results back, so a replayed answer cites the same tool calls and passes the same
number checker.

Everything recorded is what already left through the outbound scan (hashed codes and numbers);
scripts/llm_bench.py scans each fixture for canaries again before writing it.
"""
from __future__ import annotations

import json
import os
import time

import httpx

from agent.tools import Toolbox


def _json(content: bytes):
    try:
        return json.loads(content or b"null")
    except ValueError:
        return {"raw": content.decode("utf-8", "replace")}


class RecordingTransport(httpx.BaseTransport):
    def __init__(self):
        # A custom transport disables httpx's proxy-from-environment, so use HTTPS_PROXY (the
        # egress allowlist proxy) explicitly, as the default client would.
        self._inner = httpx.HTTPTransport(proxy=os.environ.get("HTTPS_PROXY") or None)
        self.exchanges: list[dict] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        started = time.monotonic()
        resp = self._inner.handle_request(request)
        content = resp.read()
        self.exchanges.append({"method": request.method, "url": str(request.url).split("?")[0],
                               "request": _json(request.content), "status": resp.status_code,
                               "response": _json(content), "seconds": round(time.monotonic() - started, 3)})
        return httpx.Response(resp.status_code, content=content, request=request)


class ReplayTransport(httpx.BaseTransport):
    def __init__(self, exchanges: list[dict]):
        self.exchanges = list(exchanges)
        self.requests: list[dict] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not self.exchanges:
            raise AssertionError("replay ran out of recorded responses")
        ex = self.exchanges.pop(0)
        assert str(request.url).split("?")[0] == ex["url"], (str(request.url), ex["url"])
        self.requests.append(_json(request.content))
        return httpx.Response(ex["status"], json=ex["response"], request=request)


class RecordingToolbox(Toolbox):
    def __init__(self):
        super().__init__()
        self.recorded: list[dict] = []

    def call(self, name: str, args: dict):
        tc, result = super().call(name, args)
        self.recorded.append({"tool_call_id": tc, "name": name, "args": args or {}, "result": result})
        return tc, result


class ReplayToolbox(Toolbox):
    def __init__(self, recorded: list[dict]):
        super().__init__()
        self.recorded = list(recorded)

    def call(self, name: str, args: dict):
        if not self.recorded:
            raise AssertionError(f"replay: unexpected extra tool call {name}")
        rec = self.recorded.pop(0)
        assert rec["name"] == name, (rec["name"], name)
        self.results[rec["tool_call_id"]] = rec["result"]
        self.calls.append({"tool_call_id": rec["tool_call_id"], "name": name})
        return rec["tool_call_id"], rec["result"]
