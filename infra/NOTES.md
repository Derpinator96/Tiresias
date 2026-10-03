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
- 2026-10-03: air-gapped mode (step 31). infra/docker-compose.airgap.yml, layered by `make airgap`, replaces ai's networks with `!override [boundary, llm-local]` (Docker Compose v2.24+, checked with v5.6.0 `config`) and sets BT_LLM_PROVIDER=ollama with an empty GEMINI_API_KEY. `make online` recreates ai from the base file. Independent of the egress proxy work: the override replaces whatever networks the base file gives ai.
- 2026-10-03: `llm-local` is an internal network with a fixed subnet 10.31.31.0/29, gateway 10.31.31.1, outside Docker's default pools (172.17.0.0/12, 192.168.0.0/16). Found empirically with Docker 29.8.2: an internal network's bridge still gets its gateway IP on the host, and a container on it reaches a host service bound to that IP, while it has no default route. Ollama (native, on the host) must bind 10.31.31.1:11434. Rejected: host-gateway (resolves to docker0, 172.17.0.1, which a container with no default route cannot reach: Errno 101) and binding Ollama to 0.0.0.0 (serves the model to the LAN and the hotspot).
- 2026-10-03: proof on bt-airgap with a host stand-in on 10.31.31.1:11434 (python3 -m http.server, then infra/tests/fake_ollama.py): from ai, the stand-in answered; generativelanguage.googleapis.com:443 failed name resolution; 1.1.1.1:443, 8.8.8.8:53, 172.17.0.1 and the host's LAN address failed with Errno 101 (network unreachable); pg-prod and pg-twin failed by name and by IP; the gateway answered. infra/tests/test_airgap_network.py (in ai) and test_airgap_q1.py (in tools) run under `make test-airgap`.
- 2026-10-03: as with `boundary` today, a container on an internal network can reach any host service listening on that bridge's IP or on 0.0.0.0; only the host, never beyond it.
- 2026-10-03: the host's Docker address pools are fully used by the parallel bt-* stacks ("all predefined address pools have been fully subnetted"), so on this machine a new auto-assigned network (for example bt-airgap_operator) cannot be created. llm-local is unaffected (fixed subnet). Dashboard tests on bt-airgap ran with a scratch override that drops the operator network and port.
- 2026-10-04: `web` service (site/web, Dockerfile in that folder, built with NEXT_PUBLIC_BT_LOCAL=1): the website with the live Ask page, 127.0.0.1:3000 only. Networks [boundary, operator], no `private` (human decision: it calls only gateway and ai). test_egress_proxy.py's set of services with an internet route now includes web (human-approved test change), plus a new test that every published port binds 127.0.0.1. Not built or started yet: Docker was not reachable from the agent session.
