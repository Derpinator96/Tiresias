# Blind Tuner

Blind Tuner recommends fixes for slow PostgreSQL queries. The AI side sees only hashed metadata, never raw values or real names. Every recommended fix is measured on a statistical twin before a DBA applies it. Entry for CodeUtsava X.0, Problem Statement 4.

Design and rules: [docs/architecture.md](docs/architecture.md) is the single source of truth. [CLAUDE.md](CLAUDE.md) holds the rules every contributor follows and the current state of each component.

## Layout

| Folder | Holds | Owner |
| --- | --- | --- |
| `contracts/` | JSON Schemas for every hand-off, plus contract tests | humans |
| `infra/` | docker-compose, Dockerfiles, Postgres config | Agent 1 |
| `db/` | QuickMart schema and generator, canaries, twin builder, sandbox | Agent 1 |
| `gateway/` | hashing, literal stripping, ingestion, ledger, canary scanner, resolver, API | Agent 2 |
| `miner/` | FP-Growth candidate miner | Agent 2 |
| `privacy_tests/` | adversarial leak test, negative control | Agent 2 |
| `models/gnn/` | runtime predictor | Agent 3 |
| `rl/` | configuration search | Agent 3 |
| `agent/` | LLM agent, tools, number checker | Agent 4 |
| `verify/` | result checksums | Agent 4 |
| `dashboard/` | Streamlit operator dashboard (local only, never public) | Agent 4 |
| `e2e/` | end-to-end scenario tests | humans |
| `scripts/` | results.json exporter | humans |
| `site/` | public static site for Vercel | humans |
| `common/` | shared config loader | humans |

Each folder has a `NOTES.md` recording its decisions.

## Commands

All Python runs inside a pinned Python 3.11 image, so the host needs only Docker and GNU make (`winget install ezwinports.make` on Windows). Without make, run the docker compose line instead. Set `DC` first (Git Bash on Windows also needs `export MSYS_NO_PATHCONV=1`):

```bash
DC="docker compose -f infra/docker-compose.yml --project-directory ."
```

| Target | Does | Without make |
| --- | --- | --- |
| `make keygen` | create `.env` with the HMAC key and Postgres password (never printed) | see the Makefile `keygen` target |
| `make up` | build and start every service | `$DC up -d --build` |
| `make down` | stop every service, keep data | `$DC down` |
| `make test` | contract and config tests | `$DC run --rm -T tools python -m pytest contracts/tests common/tests` |
| `make test-infra` | network isolation and Postgres image tests | `bash infra/tests/run.sh` |
| `make seed` | load QuickMart into pg-prod, run the Q1 workload, build the twin (about 1 minute) | `$DC run --rm -T tools python -m db.seed`, then the `twin` lines |
| `make twin` | rebuild only the twin from pg-prod's schema and pg_stats | see the Makefile `twin` target (pg_dump inside pg-twin, then `$DC run --rm -T tools python -m db.twin.build`) |
| `make test-gateway` | gateway unit and component tests | `$DC run --rm -T tools python -m pytest gateway/tests` |
| `make test-miner` | miner unit tests and the Q1 candidate check | `$DC run --rm -T tools python -m pytest miner/tests` |
| `make test-predictor` | runtime predictor tests | `$DC run --rm -T tools python -m pytest models/gnn/tests` |
| `make test-search` | greedy search, HypoPG and twin tests | `$DC run --rm -T tools python -m pytest rl/tests db/sandbox/tests db/twin/tests` |
| `make test-agent` | number checker, Gemini adapter (mocked) and agent loop | `$DC run --rm -T tools python -m pytest agent/tests/test_agent.py` |
| `make test-llm` | live Gemini checks in the ai container (needs GEMINI_API_KEY) | `$DC exec -T ai python -m pytest -p no:cacheprovider -rs agent/tests/test_live_llm.py` |
| `make test-verify` | result checksums on the twin | `$DC run --rm -T tools python -m pytest verify/tests` |
| `make demo` | start the dashboard and open http://127.0.0.1:8501 | `$DC up -d dashboard`, then open the URL |
| `make test-dashboard` | dashboard AppTest suite | `$DC exec -T dashboard python -m pytest -p no:cacheprovider /app/dashboard/tests` |
| `make e2e` | the Q1 end-to-end test; fails without GEMINI_API_KEY; a pass writes runs/latest.json | `$DC run --rm -T tools python -m pytest -p no:cacheprovider -v e2e` |
| `make test-db` | data generation checks against the seeded pg-prod | `$DC run --rm -T tools python -m pytest db/tests` |

Targets still to come:

| Target | Does | Build step |
| --- | --- | --- |
| `make export` | write results.json from the latest e2e run | 15 |
| `make site` | build the public site | 15 |

The equivalent `docker compose` command for each target will be listed here when that target exists.

## Secrets

The HMAC key and `GEMINI_API_KEY` live only in an uncommitted `.env` file. Never print, log or commit them.
