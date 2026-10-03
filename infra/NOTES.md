# infra/: notes

Owner: Agent 1

Purpose: docker-compose, Dockerfiles and Postgres config.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: networks. `private` and `boundary` are `internal: true`. `ai` also joins `egress` for the LLM API. SIMPLIFIED: egress is unrestricted internet, not an allowlist of the LLM API host. Label it SIMPLIFIED everywhere it appears.
- 2026-10-03: `dashboard` joins an `operator` network so the host can reach it; its port is bound to 127.0.0.1 only. The dashboard is never hosted publicly.
- 2026-10-03: all Python runs in one pinned Python 3.11 image (host has 3.12 and 3.14 only). The Makefile only calls `docker compose`.

## Plug-in points not built yet

- Egress allowlist proxy for `ai` (MISSING).
- Optional `ollama` service for air-gapped mode (MISSING).
