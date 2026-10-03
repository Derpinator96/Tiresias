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
- 2026-10-03: pinned versions. Postgres image `postgres:16.15-bookworm` (PG_VERSION 16.15-1.pgdg12+2) plus `postgresql-16-hypopg=1.4.3-1.pgdg12+2` from the image's PGDG apt repo. Python image `python:3.11.17-slim`. Python packages in `infra/python/requirements.lock`, compiled with `uv pip compile --python-version 3.11 --python-platform x86_64-manylinux_2_28 --generate-hashes` and installed with `--require-hashes`.
- 2026-10-03: code is bind-mounted read-only per service, not baked into the image. `ai` gets only config.yaml, contracts, common, miner, models, rl, agent, verify and infra/tests: no db/, no gateway/, no .env. `tools` mounts the whole repo; it is a private-side harness for seeding and tests, not part of the product.
- 2026-10-03: auto_explain logs JSON plans through `log_destination = jsonlog` into the `pgprod-log` volume. Only `gateway` and `tools` mount it, read-only. Tunable Postgres values (pg_stat_statements.track, auto_explain thresholds) are not in postgresql.conf; db/apply_settings.py (step 5) applies them from config.yaml with ALTER SYSTEM.
- 2026-10-03: `pg-twin` runs the same image without auto_explain preloaded, so log_analyze overhead does not distort timed twin runs.
- 2026-10-03: the gateway connects as the `postgres` superuser. SIMPLIFIED: least-privilege roles (pg_read_all_stats on prod, write access on the twin only) are pending.
- 2026-10-03: `.env` comes from `make keygen` (infra/keygen.py). It never prints keys and never overwrites an existing BT_HMAC_KEY.

## Tests

`make test-infra` runs infra/tests/run.sh:
- in `ai`: pg-prod and pg-twin fail by name and by IP (IPs from `docker inspect`); the gateway is reachable; the LLM API host is reachable (SIMPLIFIED egress, so this does not prove other hosts are blocked);
- in `gateway`: no internet route; both Postgres reachable;
- in `tools`: Postgres 16 on both; prod preloads pg_stat_statements and auto_explain; twin does not preload auto_explain; extensions installed on both; HypoPG changes a plan on both; log destination is jsonlog.
