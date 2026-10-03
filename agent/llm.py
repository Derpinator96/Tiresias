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

HTTP 429, and the transient server errors 500, 503 and 504, are retried with exponential backoff (llm.retry_* in config.yaml), honouring a
Retry-After header, else the body's RetryInfo.retryDelay, when present. Each retry is reported through on_event, which the
dashboard shows as "rate limited, retrying".

Air-gapped mode (step 31): OllamaChat talks to a local model through Ollama's POST /api/chat
(non-streaming). Shapes checked on 2026-10-03 against
https://github.com/ollama/ollama/blob/main/docs/api.md and https://docs.ollama.com/api/chat
(model, messages, format as a JSON schema, options.temperature and options.num_ctx, stream
false; response message.content, done_reason, prompt_eval_count, eval_count; errors as
{"error": ...}). The model (gemma2:2b) has no tools capability on ollama.com, so the tools are
described in the system prompt and every reply is constrained by `format` to one JSON object:
a tool call or the final answer. Its Ollama template renders only system, user and assistant
messages (a "tool" message would be dropped), so tool results go back as user messages.
Not yet run against a real Ollama: none is installed on this machine (2026-10-03).
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Callable

import httpx

from agent import gateway_client as gw
from common.config import cfg

GEMINI_HOST = "generativelanguage.googleapis.com"
GEMINI_URL = f"https://{GEMINI_HOST}/v1beta/models/{{model}}:generateContent"
PROBE_TIMEOUT_S = 3.0

# On-screen labels (dashboard): which model answers, and for the local one whether ai can still
# reach the LLM API host, checked live by llm_api_reachable(), not assumed from the mode.
LABEL_GEMINI = "LLM: {model} through the Gemini API (hashed metadata leaves this machine)"
LABEL_OLLAMA = "LLM: local model {model} through Ollama on this machine; {route}"
ROUTE_NONE = f"air-gapped: ai cannot reach {GEMINI_HOST} (checked now)"
ROUTE_OPEN = f"NOT air-gapped: ai can still reach {GEMINI_HOST} (run make airgap)"


# 429 is rate limiting; 500, 503 and 504 are transient server errors (a 503 "service
# unavailable" was seen on the first live run, 2026-10-03). All use the same backoff.
RETRYABLE = {429, 500, 503, 504}


def _reason(status: int) -> str:
    return "rate limited" if status == 429 else f"LLM service unavailable (HTTP {status})"


def _google_hint(r: httpx.Response) -> tuple[float | None, str]:
    """From a Gemini error body: RetryInfo.retryDelay ("33s") and the QuotaFailure quota IDs, per
    the google.rpc error model. Not every 429 carries them; anything unexpected gives (None, "").
    Added 2026-10-03 after a 429 that outlasted the header-less backoff (2+4+8+16 s)."""
    try:
        details = r.json()["error"]["details"]
        delay = next((float(d["retryDelay"].rstrip("s")) for d in details if "retryDelay" in d), None)
        return delay, ", ".join(v["quotaId"] for d in details for v in d.get("violations", []) if "quotaId" in v)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, ""


class MissingKey(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


class OutboundBlocked(RuntimeError):
    def __init__(self, entry: dict):
        super().__init__("LLM request blocked by the gateway's canary scan")
        self.entry = entry


class ContextOverflow(RuntimeError):
    """The conversation does not fit the local model's context. Raised instead of sending,
    because Ollama would silently drop the oldest messages (tool results the answer cites)."""


class MalformedReply(RuntimeError):
    pass


def _send(client: httpx.Client, url: str, body: str, headers: dict, on_event: Callable[[str], None],
          sleep: Callable[[float], None], owner=None) -> dict:
    """Scan and ledger the exact bytes first (fail closed), then POST them, retrying RETRYABLE.
    The ledger entry is kept on `owner.last_entry` (the adversarial test cites its payload ID)."""
    entry = gw.post("/v1/ledger/outbound", {"destination": "llm", "body": body})
    if owner is not None:
        owner.last_entry = entry
    if entry["verdict"] != "allow":
        raise OutboundBlocked(entry)
    attempts = int(cfg("llm.retry_max_attempts"))
    delay = float(cfg("llm.retry_initial_backoff_s"))
    status, quotas = 0, ""
    for attempt in range(1, attempts + 1):
        r = client.post(url, content=body.encode("utf-8"), headers={"Content-Type": "application/json", **headers})
        status = r.status_code
        if status not in RETRYABLE:
            r.raise_for_status()
            return r.json()
        hinted, quotas = _google_hint(r)
        if attempt == attempts:
            break
        retry_after = r.headers.get("Retry-After")
        wait = min(float(retry_after) if retry_after and retry_after.isdigit() else hinted or delay,
                   float(cfg("llm.retry_max_backoff_s")))
        on_event(f"{_reason(status)}, retrying in {wait:.0f} s (attempt {attempt + 1} of {attempts})")
        sleep(wait)
        delay *= float(cfg("llm.retry_backoff_multiplier"))
    on_event(f"{_reason(status)}, gave up after {attempts} attempts")
    raise RateLimited(f"LLM API returned HTTP {status} on all {attempts} attempts"
                      + (f" (quota: {quotas})" if quotas else ""))


class GeminiREST:
    def __init__(self, model: str, api_key: str, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self._key = api_key
        self._client = httpx.Client(transport=transport, timeout=120.0)
        self._sleep = sleep

    def generate(self, system: str, contents: list[dict], declarations: list[dict],
                 on_event: Callable[[str], None] = lambda _: None) -> dict:
        req = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents}
        if declarations:              # no declarations: a session with no tools at all
            req["tools"] = [{"functionDeclarations": declarations}]
            req["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        req["generationConfig"] = {"temperature": cfg("llm.temperature")}
        return _send(self._client, GEMINI_URL.format(model=self.model), json.dumps(req), {"x-goog-api-key": self._key},
                     on_event, self._sleep, owner=self)


FINAL = "final_answer"
COMPACT = (",", ":")


def reply_schema(declarations: list[dict]) -> dict:
    """Ollama `format`: every reply is one tool call or the final answer, nothing else."""
    return {"type": "object",
            "properties": {"name": {"enum": [d["name"] for d in declarations] + [FINAL]},
                           "args": {"type": "object"},
                           "answer": {"type": "string"}},
            "required": ["name", "args", "answer"]}


def tool_prompt(system: str, declarations: list[dict]) -> str:
    tools = "\n".join(f"- {d['name']}: {d['description']} Args: {json.dumps(d['parameters'].get('properties', {}))}"
                      for d in declarations)
    return (f"{system}\n\nTools:\n{tools}\n\n"
            "Reply with exactly one JSON object and nothing else. To call one tool: "
            '{"name": "<tool>", "args": {<arguments>}, "answer": ""}. '
            f'To give the final answer: {{"name": "{FINAL}", "args": {{}}, "answer": "<your answer>"}}. '
            "Each tool result comes back in a user message that starts with its tool call ID; "
            "cite that ID after every number you take from it.")


def ollama_messages(contents: list[dict]) -> list[dict]:
    """The agent's Gemini-shaped turns as Ollama messages. Tool results become user messages:
    gemma2's template drops any other role."""
    out = []
    for c in contents:
        for p in c.get("parts", []):
            if "functionCall" in p:
                fc = p["functionCall"]
                out.append({"role": "assistant", "content": json.dumps({"name": fc["name"], "args": fc.get("args", {}), "answer": ""})})
            elif "functionResponse" in p:
                fr = p["functionResponse"]
                r = fr["response"]
                out.append({"role": "user", "content": f"Result of {r['tool_call_id']} ({fr['name']}): "
                                                       f"{json.dumps(r['result'], separators=COMPACT)}"})
            elif c["role"] == "model":
                out.append({"role": "assistant", "content": json.dumps({"name": FINAL, "args": {}, "answer": p.get("text", "")})})
            else:
                out.append({"role": "user", "content": p.get("text", "")})
    return out


def parse_reply(raw: str, names: set[str]) -> dict | None:
    """One reply as a Gemini-shaped content (functionCall or text part), or None if malformed."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("args", {}), dict):
        return None
    if obj.get("name") == FINAL and isinstance(obj.get("answer"), str) and obj["answer"].strip():
        return {"role": "model", "parts": [{"text": obj["answer"]}]}
    if obj.get("name") in names:
        return {"role": "model", "parts": [{"functionCall": {"name": obj["name"], "args": obj.get("args", {})}}]}
    return None


def estimate_tokens(text: str) -> int:
    """Gemma's tokenizer splits digits (Gemma 2 report, arXiv 2408.00118), so each digit is one
    token; other characters count at llm.ollama.chars_per_token.
    ponytail: an estimate, not gemma's tokenizer (none is installed); recalibrate from the
    "prompt tokens evaluated" events of a real run."""
    digits = sum(ch.isdigit() for ch in text)
    return digits + int((len(text) - digits) / float(cfg("llm.ollama.chars_per_token")))


class OllamaChat:
    """A local model through Ollama's POST /api/chat. Same generate() contract as GeminiREST,
    so the tool loop, the number checker and the ledger path are unchanged."""

    def __init__(self, model: str, base_url: str, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.url = base_url.rstrip("/") + "/api/chat"
        self._client = httpx.Client(transport=transport, timeout=float(cfg("llm.ollama.timeout_s")))
        self._sleep = sleep

    def generate(self, system: str, contents: list[dict], declarations: list[dict],
                 on_event: Callable[[str], None] = lambda _: None) -> dict:
        num_ctx, num_predict = int(cfg("llm.ollama.num_ctx")), int(cfg("llm.ollama.num_predict"))
        names = {d["name"] for d in declarations}
        messages = [{"role": "system", "content": tool_prompt(system, declarations)}] + ollama_messages(contents)
        retries = int(cfg("llm.ollama.malformed_retries"))
        for attempt in range(retries + 1):
            chars = sum(len(m["content"]) for m in messages)
            est = sum(estimate_tokens(m["content"]) for m in messages)
            if est + num_predict > num_ctx:
                raise ContextOverflow(f"prompt of {chars} characters (about {est} tokens) plus {num_predict} reply tokens "
                                      f"exceeds the local model's context of {num_ctx} tokens; not sent, because Ollama "
                                      "would silently drop the oldest messages")
            body = json.dumps({"model": self.model, "messages": messages, "stream": False,
                               "format": reply_schema(declarations),
                               "options": {"temperature": cfg("llm.temperature"), "num_ctx": num_ctx,
                                           "num_predict": num_predict}})
            resp = _send(self._client, self.url, body, {}, on_event, self._sleep, owner=self)
            used = resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0)
            on_event(f"local model: prompt {chars} characters, about {est} tokens estimated, "
                     f"{resp.get('prompt_eval_count', 0)} prompt tokens evaluated, {resp.get('eval_count', 0)} generated")
            if used >= num_ctx:
                raise ContextOverflow(f"Ollama used {used} of {num_ctx} context tokens; it may have dropped messages")
            raw = resp.get("message", {}).get("content", "")
            content = parse_reply(raw, names)
            if content is not None:
                return {"candidates": [{"content": content}]}
            on_event(f"local model reply was not one valid JSON tool call or answer (attempt {attempt + 1} of {retries + 1})")
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": "That reply was not one JSON object in the required "
                                                               "format. Reply again with exactly one JSON object."}]
        raise MalformedReply(f"local model gave no valid JSON reply in {retries + 1} attempts")


def provider_name() -> str:
    """llm.provider from config.yaml, unless make airgap set BT_LLM_PROVIDER on the ai service."""
    return os.environ.get("BT_LLM_PROVIDER") or cfg("llm.provider")


def provider(transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep):
    """The configured provider. Gemini's key is read from the env var named in config.yaml."""
    name = provider_name()
    if name == "ollama":
        return OllamaChat(cfg("llm.ollama.model"), cfg("llm.ollama.base_url"), transport, sleep)
    if name != "gemini":
        raise ValueError(f"unknown llm.provider {name!r}")
    key = os.environ.get(cfg("llm.api_key_env"), "")
    if not key:
        raise MissingKey(f"{cfg('llm.api_key_env')} is not set")
    return GeminiREST(cfg("llm.model"), key, transport, sleep)


def llm_api_reachable() -> bool:
    try:
        socket.create_connection((GEMINI_HOST, 443), timeout=PROBE_TIMEOUT_S).close()
        return True
    except OSError:
        return False


def label() -> str:
    if provider_name() == "ollama":
        return LABEL_OLLAMA.format(model=cfg("llm.ollama.model"), route=ROUTE_OPEN if llm_api_reachable() else ROUTE_NONE)
    return LABEL_GEMINI.format(model=cfg("llm.model"))
