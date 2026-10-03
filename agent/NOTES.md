# agent/: notes

Owner: Agent 4

Purpose: LLM agent with tool calling, system rules and the number checker.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: provider is the Google Gemini API, a Flash model. The exact model name lives in config.yaml and is taken from the current model list, not guessed. Key in env var `GEMINI_API_KEY`.
- 2026-10-03: the LLM sits behind a provider adapter; provider and model are config values.
- 2026-10-03: HTTP 429 is retried with backoff. The dashboard shows "rate limited, retrying" instead of failing silently.
- 2026-10-03: every LLM request body goes through `POST /v1/ledger/outbound` first and is sent only on allow.

## Plug-in points not built yet

- Tools gnn_explain, rewrite_candidates and verify (MISSING).
- RAG over R-Bot rules (MISSING).
- Air-gapped mode via Ollama (MISSING).
- 2026-10-03: Gemini is called through its REST API (generateContent) with httpx, not the google-genai SDK, so the exact request bytes are known. Each body goes to the gateway's /v1/ledger/outbound first and is sent only on verdict allow. Request and response shapes were checked against https://ai.google.dev/api/generate-content on 2026-10-03; that page's examples use gemini-3.8-flash. The function-calling guide page now documents the newer Interactions API (input, previous_interaction_id); generateContent remains documented in the API reference and is what this code uses.
- 2026-10-03: the model's turn is sent back unchanged in the next request, so thoughtSignature parts are returned as the API requires. functionResponse carries the call's id when the model gave one.
- 2026-10-03: HTTP 429: exponential backoff from llm.retry_initial_backoff_s, multiplied by llm.retry_backoff_multiplier, capped at llm.retry_max_backoff_s, honouring Retry-After; llm.retry_max_attempts attempts. Each retry emits "rate limited, retrying in N s (attempt a of b)"; exhaustion emits "rate limited, gave up after b attempts" and /ai/ask returns 503 with the events. The dashboard polls GET /ai/ask/{question_id}/events.
- 2026-10-03: five tools for the skeleton (get_slow_templates, get_plan, mine_candidates, run_rl, simulate). gnn_explain, rewrite_candidates and verify are MISSING. simulate adds speedup_pct computed by code, so the LLM can cite a percentage instead of computing one (rule 2).
- 2026-10-03: the LLM receives only the question_id and the template IDs the gateway's resolver matched, never the DBA's question text.
- 2026-10-03: number checker. Every number must be followed by a [tc_xxxxxxxx] tag and match a numeric leaf of that call's result, rounded to the decimals written. Code digits are ignored. One retry with feedback (llm.checker_retries), then the answer is blocked (status blocked_by_checker, no text shown). Tags are stripped from the displayed text and kept in Answer.numbers.
- 2026-10-03: live LLM path UNTESTED: GEMINI_API_KEY was not set. agent/tests/test_live_llm.py (run in the ai container) checks llm.model against the API's model list and runs a live Q1 answer through the checker; it skips with its reason until the key exists.
