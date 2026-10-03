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

## Step 27: egress allowlist proxy (2026-10-03)

- Supersedes the SIMPLIFIED egress decision and the "Egress allowlist proxy for `ai` (MISSING)" plug-in line above. ai is no longer on `egress`. It shares only the new internal network `ai-proxy` with the `egress-proxy` service, which alone sits on `egress` (internet). ai reaches the LLM API through `HTTPS_PROXY=http://egress-proxy:3128`; gateway, dashboard and tools are on neither network.
- Proxy: infra/egress_proxy.py, about 60 lines of stdlib asyncio, run in blind-tuner-python:local (no new image, no pull, no apt). HTTP CONNECT only, deny by default: 200 only for a host in `egress.allowed_hosts` and a port in `egress.allowed_ports` (config.yaml: generativelanguage.googleapis.com, 443); 403 for any other host, port or IP literal; 405 for any other method (no plain forwarding); 400 for a malformed request; 502 if the upstream connect fails. Host match is exact after lowercasing and dropping a trailing dot (so `api.example.test.evil.test` does not match). Each decision prints `allow|deny status host:port`, never content.
- Why not tinyproxy: it needs a new image and apt over a slow network, and its config (Allow, ConnectPort, Filter with FilterDefaultDeny) spreads the decision over three settings. The stdlib proxy's whole allow rule is one function, `decide`, unit-tested, and it reads the same config.yaml as everything else.
- SIMPLIFIED, labelled on screen (LABEL in infra/egress_proxy.py = dashboard LABELS["egress"]): the proxy checks the host name in the CONNECT line, not the traffic inside TLS; SNI and the Host header are not compared with it. No idle timeout on an open tunnel (LLM calls can run for minutes).
- httpx 0.28.1 (checked in the image): Client and the module functions default to trust_env=True and read HTTPS_PROXY through urllib's getproxies(), mounting it for https:// only; a client built with an explicit transport ignores env proxies (only tests do that). http://gateway:8000 therefore stays direct. No code change was needed in agent/llm.py for the proxy.
- Air-gapped mode (later, not built): with `llm.provider: ollama` the internet route can be dropped by taking `egress-proxy` off `egress` or emptying `egress.allowed_hosts` (an empty list denies everything). A host-native Ollama is a separate route the proxy does not cover.
- infra/tests/run.sh reads the private network name from `${COMPOSE_PROJECT_NAME:-blind-tuner}_private`, so it runs on any compose project, and it now also runs test_private_no_internet.py in tools.
- Tests: test_isolation.py in ai (13): Postgres unreachable by name and IP; gateway reachable; the LLM host reachable through the proxy (CONNECT 200; this test used to open a direct socket, the brief asked for it to go through the proxy); example.com, the LLM host on port 80 and 1.1.1.1 refused by the proxy (403), a GET refused (405); no direct route to the LLM host, example.com or 1.1.1.1. test_private_no_internet.py in gateway and tools (3 each): no internet, and the proxy itself is out of reach. infra/tests/test_egress_proxy.py in tools (make test-all): `decide` table, a real tunnel relaying bytes on 127.0.0.1 and refusing another port, the allowlist equals agent/llm.py's GEMINI_URL host, and compose wiring (only egress-proxy and the 127.0.0.1-bound dashboard have a non-internal network; only ai and the proxy are on ai-proxy).
- dashboard mounts ./runs read-only for the adversarial leak test result (counts only, no names).
- The proxy adds one Docker network per stack (5 with the dashboard). With many compose projects on one host, Docker's default address pools ran out on 2026-10-03 ("all predefined address pools have been fully subnetted" when creating bt-privacy_operator); the dashboard tests then ran in a plain `docker run` on bt-privacy_boundary with the dashboard's mounts. One stack per machine is unaffected.
