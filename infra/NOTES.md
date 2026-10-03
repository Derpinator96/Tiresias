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
- 2026-10-03: `verieql` service (step 21): VeriEQL v1.0 (commit 3b99928bf976c11cb59c9db6a177adba21f75798) in its own image, infra/verieql/. Licence CC BY-NC-SA 4.0 (non-commercial, share-alike): human decision "use it, isolated". None of its code is copied into this MIT repo; it is cloned at build time and called over HTTP by our stdlib wrapper verify/verieql_server.py (mounted read-only). MUST be replaced before any commercial use. Private network only (it sees real SQL), no internet.
- 2026-10-03: VeriEQL needs z3-solver 4.13.0.0 plus its patched z3py_libs copied over the z3 package (as its README instructs); with a newer z3 it fails with `And() got an unexpected keyword argument 'ctx'`. The image passes VeriEQL's own `python -m test.test_env`.
- 2026-10-03: air-gapped mode (step 31). infra/docker-compose.airgap.yml, layered by `make airgap`, replaces ai's networks with `!override [boundary, llm-local]` (Docker Compose v2.24+, checked with v5.6.0 `config`) and sets BT_LLM_PROVIDER=ollama with an empty GEMINI_API_KEY. `make online` recreates ai from the base file. Independent of the egress proxy work: the override replaces whatever networks the base file gives ai.
- 2026-10-03: `llm-local` is an internal network with a fixed subnet 10.31.31.0/29, gateway 10.31.31.1, outside Docker's default pools (172.17.0.0/12, 192.168.0.0/16). Found empirically with Docker 29.8.2: an internal network's bridge still gets its gateway IP on the host, and a container on it reaches a host service bound to that IP, while it has no default route. Ollama (native, on the host) must bind 10.31.31.1:11434. Rejected: host-gateway (resolves to docker0, 172.17.0.1, which a container with no default route cannot reach: Errno 101) and binding Ollama to 0.0.0.0 (serves the model to the LAN and the hotspot).
- 2026-10-03: proof on bt-airgap with a host stand-in on 10.31.31.1:11434 (python3 -m http.server, then infra/tests/fake_ollama.py): from ai, the stand-in answered; generativelanguage.googleapis.com:443 failed name resolution; 1.1.1.1:443, 8.8.8.8:53, 172.17.0.1 and the host's LAN address failed with Errno 101 (network unreachable); pg-prod and pg-twin failed by name and by IP; the gateway answered. infra/tests/test_airgap_network.py (in ai) and test_airgap_q1.py (in tools) run under `make test-airgap`.
- 2026-10-03: as with `boundary` today, a container on an internal network can reach any host service listening on that bridge's IP or on 0.0.0.0; only the host, never beyond it.
- 2026-10-03: the host's Docker address pools are fully used by the parallel bt-* stacks ("all predefined address pools have been fully subnetted"), so on this machine a new auto-assigned network (for example bt-airgap_operator) cannot be created. llm-local is unaffected (fixed subnet). Dashboard tests on bt-airgap ran with a scratch override that drops the operator network and port.
