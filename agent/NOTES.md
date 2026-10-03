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
