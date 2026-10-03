# gateway/: notes

Owner: Agent 2

Purpose: HMAC hashing, literal stripping, ingestion, rounding, payload ledger, canary scanner, question resolver, dehash and the gateway API.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: the HMAC key is read from the uncommitted `.env` only. Never print, log or commit it.

## Plug-in points not built yet

- `POST /v1/approve` with migration and rollback scripts (MISSING).
