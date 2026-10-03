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

NVIDIA NIM and OpenAI: OpenAIChat (NimChat for NIM), see its docstring. Same send path
(_send), same retries.

Fallback (human decision 2026-10-03): chain() lists llm.provider then llm.fallback; agent/api.py
asks the whole question again of the next provider when one fails (FAILOVER_ERRORS). Switching
mid-conversation is not done: Gemini 3 validates thought signatures on function calls, which
calls made by another model do not carry, and Gemini's calls may have no ID while OpenAI's
format needs one.
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
from typing import Callable
from urllib.parse import urlsplit

import httpx

from agent import gateway_client as gw
from common.config import cfg

GEMINI_HOST = "generativelanguage.googleapis.com"
GEMINI_URL = f"https://{GEMINI_HOST}/v1beta/models/{{model}}:generateContent"
PROBE_TIMEOUT_S = 3.0

# On-screen labels (dashboard): which model answers, and for the local one whether ai can still
# reach the LLM API host, checked live by llm_api_reachable(), not assumed from the mode.
LABEL_GEMINI = "LLM: {model} through the Gemini API (hashed metadata leaves this machine)"
LABEL_NIM = "LLM: {model} through NVIDIA NIM (hashed metadata leaves this machine)"
LABEL_OPENAI = "LLM: {model} through the OpenAI API (hashed metadata leaves this machine)"
LABEL_OLLAMA = "LLM: local model {model} through Ollama on this machine; {route}"
ROUTE_NONE = "air-gapped: ai cannot reach any hosted LLM API (checked now)"
ROUTE_OPEN = "NOT air-gapped: ai can still reach a hosted LLM API (run make airgap)"


# 429 is rate limiting; 500, 503 and 504 are transient server errors (a 503 "service
# unavailable" was seen on the first live run, 2026-10-03). All use the same backoff.
RETRYABLE = {429, 500, 503, 504}
# Connection failures before any reply (the egress proxy answers 502 when it cannot reach the
# LLM host; seen as bursts against integrate.api.nvidia.com on 2026-10-03) use the same backoff.
# A read timeout is not retried: the request may still be running upstream.
RETRYABLE_ERRORS = (httpx.ConnectError, httpx.ProxyError)


def _reason(status: int) -> str:
    if status == 0:
        return "LLM host unreachable (connection failed)"
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
    status, quotas, error = 0, "", None
    for attempt in range(1, attempts + 1):
        try:
            r = client.post(url, content=body.encode("utf-8"), headers={"Content-Type": "application/json", **headers})
        except RETRYABLE_ERRORS as e:
            r, status, error, hinted = None, 0, e, None
        else:
            status, error = r.status_code, None
            if status not in RETRYABLE:
                r.raise_for_status()
                return r.json()
            hinted, quotas = _google_hint(r)
        if attempt == attempts:
            break
        retry_after = r.headers.get("Retry-After") if r is not None else None
        wait = min(float(retry_after) if retry_after and retry_after.isdigit() else hinted or delay,
                   float(cfg("llm.retry_max_backoff_s")))
        on_event(f"{_reason(status)}, retrying in {wait:.0f} s (attempt {attempt + 1} of {attempts})")
        sleep(wait)
        delay *= float(cfg("llm.retry_backoff_multiplier"))
    on_event(f"{_reason(status)}, gave up after {attempts} attempts")
    if error is not None:
        raise error
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


THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def nim_messages(system: str, contents: list[dict]) -> list[dict]:
    """The agent's Gemini-shaped turns as OpenAI chat messages: a model turn with function calls
    becomes one assistant message with tool_calls (arguments as a JSON string, as OpenAI
    requires), and each function response becomes a role "tool" message with its call's id."""
    out = [{"role": "system", "content": system}]
    for c in contents:
        parts = c.get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        responses = [p["functionResponse"] for p in parts if "functionResponse" in p]
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        if c["role"] == "model":
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = [{"id": fc["id"], "type": "function",
                                      "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args", {}))}}
                                     for fc in calls]
            out.append(msg)
        elif responses:
            out += [{"role": "tool", "tool_call_id": fr["id"], "content": json.dumps(fr["response"], separators=COMPACT)}
                    for fr in responses]
        else:
            out.append({"role": "user", "content": text})
    return out


def nim_content(message: dict, names: set[str]) -> tuple[dict, list[str]]:
    """One OpenAI reply message as a Gemini-shaped content, plus any tool-call errors (malformed
    arguments, unknown tool names). A call with bad arguments is passed on with empty
    arguments, so the tool reports the problem to the model; it is still counted here."""
    errors, parts = [], []
    for n, tc in enumerate(message.get("tool_calls") or []):
        fn = tc.get("function", {})
        name, raw = fn.get("name", ""), fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if not isinstance(args, dict):
                raise ValueError("arguments are not a JSON object")
        except ValueError as e:
            errors.append(f"{name}: malformed arguments ({e})")
            args = {}
        if name not in names:
            errors.append(f"unknown tool {name!r}")
        parts.append({"functionCall": {"id": tc.get("id") or f"call_{n}", "name": name, "args": args}})
    if not parts:
        # Reasoning-style models may wrap thoughts in <think>...</think>; only the rest is the answer.
        text = THINK_RE.sub("", message.get("content") or "").strip()
        parts.append({"text": text})
    return {"role": "model", "parts": parts}, errors


class OpenAIChat:
    """An OpenAI-format POST {base_url}/chat/completions with tools: NVIDIA NIM (section "nim")
    or OpenAI itself (section "openai"); llm.<section>.* holds the base URL, token cap and its
    request field name, timeout and request spacing. Same generate() contract as GeminiREST, so
    the tool loop, the number checker and the ledger path are unchanged: every request body goes
    through _send (outbound scan, fail closed).

    Shapes per NVIDIA's NIM docs (Tool Calling and MCP Integration, checked 2026-10-03: OpenAI
    tools format through vLLM's tool calling) and the OpenAI chat completions format: request
    model, messages, tools[{type: function, function}], tool_choice auto, temperature,
    max_tokens; reply choices[0].message with content and tool_calls[{id, type, function: {name,
    arguments as a JSON string}}]; tool results as role "tool" messages with tool_call_id.
    Tool calling works only on hosted models deployed with a tool-call parser, which the model
    list does not say, so make llm-bench probes each candidate. NIM run live on 2026-10-03.
    OpenAI: the same request and reply shapes (OpenAI chat completions API reference), except
    that its reference marks max_tokens deprecated in favour of max_completion_tokens
    (llm.openai.max_tokens_field). UNVERIFIED live: no OPENAI_API_KEY yet (2026-10-03)."""

    section = "openai"
    title = "OpenAI"

    def __init__(self, model: str, api_key: str, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.model = model
        self.base_url = cfg(f"llm.{self.section}.base_url").rstrip("/")
        self.url = self.base_url + "/chat/completions"
        self._key = api_key
        self._client = httpx.Client(transport=transport, timeout=float(cfg(f"llm.{self.section}.timeout_s")))
        self._sleep, self._clock = sleep, clock
        self._last = None
        self.tool_call_errors: list[str] = []

    def generate(self, system: str, contents: list[dict], declarations: list[dict],
                 on_event: Callable[[str], None] = lambda _: None) -> dict:
        sec = f"llm.{self.section}"
        req = {"model": self.model, "messages": nim_messages(system, contents)}
        if cfg(f"{sec}.send_temperature"):
            req["temperature"] = cfg("llm.temperature")
        req[cfg(f"{sec}.max_tokens_field")] = int(cfg(f"{sec}.max_tokens"))
        if declarations:
            req["tools"] = [{"type": "function", "function": d} for d in declarations]
            req["tool_choice"] = "auto"
        gap = float(cfg(f"{sec}.min_request_interval_s"))
        if self._last is not None and self._clock() - self._last < gap:   # stay under the per-minute quota
            self._sleep(gap - (self._clock() - self._last))
        self._last = self._clock()
        resp = _send(self._client, self.url, json.dumps(req), {"Authorization": f"Bearer {self._key}"},
                     on_event, self._sleep, owner=self)
        try:
            choice = resp["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise MalformedReply(f"{self.title} reply has no choices[0].message") from None
        if choice.get("finish_reason") == "length":
            on_event(f"{self.title} reply cut at the token cap ({cfg(sec + '.max_tokens')})")
        content, errors = nim_content(message, {d["name"] for d in declarations})
        for e in errors:
            on_event(f"tool-call error: {e}")
        self.tool_call_errors += errors
        return {"candidates": [{"content": content}]}

    def list_models(self) -> list[str]:
        """GET {base_url}/models. It carries no request body, so there is nothing to scan or
        ledger; the response holds model IDs only."""
        r = self._client.get(self.base_url + "/models",
                             headers={"Authorization": f"Bearer {self._key}"})
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))


class NimChat(OpenAIChat):
    section = "nim"
    title = "NIM"


PROVIDERS = ("gemini", "openai", "nim", "ollama")
HOSTED = ("gemini", "openai", "nim")
OPENAI_FORMAT = {"nim": NimChat, "openai": OpenAIChat}
# A provider failure that the next provider in chain() can answer instead. Never OutboundBlocked:
# a body the canary scan blocked must not be sent anywhere (fail closed).
FAILOVER_ERRORS = (MissingKey, RateLimited, MalformedReply, httpx.TransportError, httpx.HTTPStatusError)


def provider_name() -> str:
    """llm.provider from config.yaml, unless make airgap set BT_LLM_PROVIDER on the ai service."""
    return os.environ.get("BT_LLM_PROVIDER") or cfg("llm.provider")


def provider(transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep,
             name: str | None = None, model: str | None = None):
    """The configured provider, or `name` and `model` when given (the benchmark and the
    per-provider e2e test use these; production switches provider in config.yaml only).
    API keys are read from the env vars named in config.yaml."""
    name = name or provider_name()
    if name == "ollama":
        return OllamaChat(model or cfg("llm.ollama.model"), cfg("llm.ollama.base_url"), transport, sleep)
    if name in OPENAI_FORMAT:
        env = cfg(f"llm.{name}.api_key_env")
        key = os.environ.get(env, "")
        if not key:
            raise MissingKey(f"{env} is not set")
        model = model or cfg(f"llm.{name}.model")
        if not model:
            raise MissingKey(f"llm.{name}.model is empty in config.yaml: choose one with scripts/llm_bench.py")
        return OPENAI_FORMAT[name](model, key, transport, sleep)
    if name != "gemini":
        raise ValueError(f"unknown llm.provider {name!r}")
    key = os.environ.get(cfg("llm.api_key_env"), "")
    if not key:
        raise MissingKey(f"{cfg('llm.api_key_env')} is not set")
    return GeminiREST(model or cfg("llm.model"), key, transport, sleep)


def chain(name: str | None = None) -> list[str]:
    """Providers to try for one answer, in order. An explicit `name` (benchmark, per-provider
    e2e test) and air-gapped mode are never failed over; otherwise llm.provider then
    llm.fallback, without repeats."""
    if name:
        return [name]
    first = provider_name()
    if os.environ.get("BT_LLM_PROVIDER") or first == "ollama":
        return [first]
    out = [first]
    for n in cfg("llm.fallback"):
        if n not in HOSTED:
            raise ValueError(f"llm.fallback holds {n!r}: only hosted providers {HOSTED} can be fallbacks")
        if n not in out:
            out.append(n)
    return out


def nim_host() -> str:
    return urlsplit(cfg("llm.nim.base_url")).hostname


def openai_host() -> str:
    return urlsplit(cfg("llm.openai.base_url")).hostname


def llm_api_reachable() -> bool:
    """True if ai can open a TCP connection to any hosted LLM API (Gemini, NIM or OpenAI)."""
    for host in (GEMINI_HOST, nim_host(), openai_host()):
        try:
            socket.create_connection((host, 443), timeout=PROBE_TIMEOUT_S).close()
            return True
        except OSError:
            continue
    return False


def label() -> str:
    name = provider_name()
    if name == "ollama":
        return LABEL_OLLAMA.format(model=cfg("llm.ollama.model"), route=ROUTE_OPEN if llm_api_reachable() else ROUTE_NONE)
    if name == "nim":
        return LABEL_NIM.format(model=cfg("llm.nim.model") or "(not chosen yet)")
    if name == "openai":
        return LABEL_OPENAI.format(model=cfg("llm.openai.model") or "(not chosen yet)")
    return LABEL_GEMINI.format(model=cfg("llm.model"))
