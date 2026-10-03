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
| `make test-all` | every suite in the tools container | `$DC run --rm -T tools python -m pytest -p no:cacheprovider contracts/tests common/tests db/tests gateway/tests miner/tests models/gnn/tests rl/tests db/sandbox/tests db/twin/tests agent/tests verify/tests scripts/tests` |
| `make test-infra` | network isolation and Postgres image tests | `bash infra/tests/run.sh` |
| `make seed` | load QuickMart into pg-prod, run the Q1 workload, build the twin (about 1 minute) | `$DC run --rm -T tools python -m db.seed`, then the `twin` lines |
| `make twin` | rebuild only the twin from pg-prod's schema and pg_stats; needs gateway and ai up (it asks the miner which column pairs to keep correlated) | see the Makefile `twin` target (pg_dump inside pg-twin, then `$DC run --rm -T tools python -m db.twin.build`) |
| `make fidelity` | twin fidelity per query (twin speedup / pg-prod speedup); builds each configuration's indexes on pg-prod only while measuring, drops them, then checks pg-prod has primary key indexes only | `$DC run --rm -T tools python -m db.sandbox.fidelity`, then `$DC run --rm -T tools python -m pytest db/tests/test_quickmart.py::test_only_primary_key_indexes` |
| `make test-gateway` | gateway unit and component tests | `$DC run --rm -T tools python -m pytest gateway/tests` |
| `make test-miner` | miner unit tests and the Q1 candidate check | `$DC run --rm -T tools python -m pytest miner/tests` |
| `make test-predictor` | runtime predictor tests | `$DC run --rm -T tools python -m pytest models/gnn/tests` |
| `make test-search` | greedy search, HypoPG and twin tests | `$DC run --rm -T tools python -m pytest rl/tests db/sandbox/tests db/twin/tests` |
| `make test-agent` | number checker, Gemini and Ollama adapters (mocked) and agent loop | `$DC run --rm -T tools python -m pytest agent/tests/test_agent.py agent/tests/test_ollama.py` |
| `make test-llm` | live Gemini checks in the ai container (needs GEMINI_API_KEY) | `$DC exec -T ai python -m pytest -p no:cacheprovider -rs agent/tests/test_live_llm.py` |
| `make test-verify` | result checksums on the twin | `$DC run --rm -T tools python -m pytest verify/tests` |
| `make demo` | start the dashboard and open http://127.0.0.1:8501 | `$DC up -d dashboard`, then open the URL |
| `make drift-demo` | switch the workload mix to the Q4 drift query over about 10 minutes (demo window 120 s); the dashboard's drift panel shows the trigger and the re-tuned recommendation | `$DC run --rm -T tools python -m db.drift_demo` |
| `make test-dashboard` | dashboard AppTest suite | `$DC exec -T dashboard python -m pytest -p no:cacheprovider /app/dashboard/tests` |
| `make e2e` | the Q1 end-to-end test; fails without GEMINI_API_KEY; a pass writes runs/latest.json | `$DC run --rm -T tools python -m pytest -p no:cacheprovider -v e2e` |
| `make e2e-offline` | the offline end-to-end scenarios, no LLM API call: unparsable query withheld, invented number blocked (ai recreated in air-gapped mode against the scripted stand-in `e2e/standin_llm.py`, run with the host's `python3`, then put back online), Q4 drift on the configured window (14 minutes measured on a loaded machine) | see the Makefile `e2e-offline` target |
| `make export` | write site/results.json from the latest passing e2e run; refuses if none | `$DC run --rm -T tools python -m scripts.export_results` |
| `make site` | build the public site into site/dist | `$DC run --rm -T tools python site/build.py` |
| `make test-site` | exporter and site build tests | `$DC run --rm -T tools python -m pytest scripts/tests` |
| `make llm-models` | list NVIDIA NIM models and the tool-calling candidates (needs NVIDIA_API_KEY) | `$DC run --rm -T tools python -m scripts.llm_bench models` |
| `make llm-bench` | run Q1 on each NIM candidate, one after another, and record replay fixtures | `$DC run --rm -T tools python -m scripts.llm_bench run --provider nim` |
| `make llm-bench-gemini` | same for the configured Gemini model | `$DC run --rm -T tools python -m scripts.llm_bench run --provider gemini` |
| (no target) | run Q1 on one OpenAI model (needs OPENAI_API_KEY) | `$DC run --rm -T tools python -m scripts.llm_bench run --provider openai --models <id>` |
| `make test-db` | data generation checks against the seeded pg-prod | `$DC run --rm -T tools python -m pytest db/tests` |
| `make plans-load` | build the bench image (DSB and TPC-H kits at pinned commits), start pg-bench, load dsb, tpch and a QuickMart copy | `$DC build pg-prod`, `$DC --profile bench up -d pg-bench`, `$DC --profile bench build bench`, then `$DC --profile bench run --rm -T bench python -m db.plangen load` |
| `make plans-sample` | the early sample of 200 plans into `data/plans/sample_200.jsonl` | `$DC --profile bench run --rm -T bench python -m db.plangen sample` |
| `make plans` | every template x parameter set x index setup into `data/plans/`, then dedupe; rerun to resume | `$DC --profile bench run --rm -T bench python -m db.plangen run` |
| `make plans-dedupe` | rebuild `plans.jsonl` and `summary.json` from `plans_raw.jsonl` | `$DC --profile bench run --rm -T bench python -m db.plangen dedupe` |
| `make test-plangen` | plan generation unit and component tests | `$DC --profile bench run --rm -T bench python -m pytest -p no:cacheprovider db/plangen/tests` |
| `make gnn-export` / `make gnn-export-sample` | write the numbers-only GNN dataset and the template split to `data/gnn/` (from all plans, or from the 200-plan sample) | `$DC --profile bench run --rm -T bench python -m db.plangen export` (add `sample`) |
| `make gnn-train-ref` | reference training loop into `models/gnn/weights/` (the trainer delivers the real weights) | `$DC run --rm -T tools python -m models.gnn.train` |
| `make gnn-eval` | score the GNN and both baselines on unseen templates into `models/gnn/results.json` | `$DC run --rm -T tools python -m models.gnn.evaluate` |
| `make airgap` | recreate `ai` with the local model through Ollama and no internet route (see "Air-gapped mode" below) | `$DC -f infra/docker-compose.airgap.yml up -d --no-deps ai` |
| `make online` | recreate `ai` with the default provider (Gemini) | `$DC up -d --no-deps ai` |
| `make test-airgap` | `make airgap`, then the isolation proof inside `ai` and Q1 answered through the local model (skips only if Ollama is unreachable) | see the Makefile `test-airgap` target |

Targets still to come:

| Target | Does | Build step |
| --- | --- | --- |

The equivalent `docker compose` command for each target will be listed here when that target exists.

## Air-gapped mode

The AI side can run on a local model, so not even hashed metadata leaves the machine. Ollama runs natively on the host (Docker here has no GPU runtime) and serves `gemma2:2b` (config `llm.ollama.model`). `make airgap` recreates only the `ai` container: it joins the internal networks `boundary` (the gateway) and `llm-local` (the host's Ollama at 10.31.31.1:11434), loses its internet network, and gets no Gemini key. `make online` puts it back. `make up` also puts it back, since it recreates `ai` from the base file.

One-time host setup, by a human (official docs: https://docs.ollama.com/linux and https://docs.ollama.com/faq):

1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`. For the GPU, the NVIDIA driver must already work (`nvidia-smi`).
2. Pull the model while Ollama still listens on its default 127.0.0.1:11434: `ollama pull gemma2:2b` (about 1.6 GB).
3. Make Ollama listen on the `llm-local` gateway address instead, and turn off its cloud features: run `sudo systemctl edit ollama` and add

   ```ini
   [Unit]
   After=docker.service

   [Service]
   Environment="OLLAMA_HOST=10.31.31.1:11434"
   Environment="OLLAMA_NO_CLOUD=1"
   ```

   then `sudo systemctl daemon-reload && sudo systemctl restart ollama`. The address 10.31.31.1 exists only while the `llm-local` Docker network exists, so run `make airgap` once first; until the address exists Ollama fails to bind and systemd retries every 3 seconds (the official unit has `Restart=always`, `RestartSec=3`). The CLI now needs the address too: `OLLAMA_HOST=10.31.31.1:11434 ollama list`.
4. Check from the host: `curl http://10.31.31.1:11434/api/tags` lists `gemma2:2b`.
5. `make test-airgap`. It proves `ai` cannot reach the Gemini API host, the internet by IP, or either Postgres, then asks the Q1 question through the local model and fails unless the answer passes the number checker. `make online` afterwards to return to Gemini.

Do not bind Ollama to 0.0.0.0: that serves the model to the LAN and to the laptop's hotspot.

## Secrets

The HMAC key and `GEMINI_API_KEY` live only in an uncommitted `.env` file. Never print, log or commit them.

## Deploying the public site

Only `site/dist` is public. It is static HTML with no database access. After `make export` and `make site`:

```bash
npm i -g vercel
vercel login
cd site/dist
vercel link --yes --project blind-tuner
vercel deploy --prod
```

If the production URL is not `blind-tuner.vercel.app` (the name is taken), rename the project to `blind-tuner-demo` and deploy again. Never deploy the operator dashboard.
