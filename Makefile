# Blind Tuner. Every target only calls docker compose; all Python runs in the pinned image.
# Targets are added step by step; see PLAN.md. The README lists the plain docker compose
# line for each target, for machines without make.

export MSYS_NO_PATHCONV := 1
DC := docker compose -f infra/docker-compose.yml --project-directory .
TOOLS := $(DC) run --rm -T tools
BENCH := $(DC) --profile bench run --rm -T bench

.PHONY: keygen up down seed twin fidelity demo drift-demo e2e adversarial export site gnn-export gnn-export-sample gnn-train-ref gnn-eval plans-load plans-sample plans plans-dedupe test-plangen test test-all test-site test-agent test-llm test-verify test-dashboard test-infra test-db test-gateway test-miner test-predictor test-search airgap online test-airgap

## Create .env with the HMAC key and Postgres password (never printed, never overwritten).
keygen:
	docker run --rm -v "$(CURDIR):/repo" -w /repo -e PYTHONPATH=/repo python:3.11.17-slim \
		sh -c "pip install -q --root-user-action=ignore pyyaml==6.0.3 && python infra/keygen.py"

## Build and start every service.
up:
	$(DC) up -d --build

## Stop every service. Data volumes are kept.
down:
	$(DC) down

## Load QuickMart into pg-prod, apply settings from config.yaml, run the Q1 workload,
## then build the twin.
seed:
	$(TOOLS) python -m db.seed
	$(MAKE) twin

## Copy pg-prod's schema to pg-twin with pg_dump --schema-only (run inside pg-twin, which has
## pg_dump 16), then fill it with synthetic rows from pg_stats.
twin:
	$(DC) exec -T pg-twin sh -c 'PGPASSWORD="$$POSTGRES_PASSWORD" pg_dump -h pg-prod -U postgres --schema-only --clean --if-exists --no-owner --no-privileges quickmart | psql -q -v ON_ERROR_STOP=1 -U postgres -d quickmart_twin >/dev/null'
	$(TOOLS) python -m db.twin.build

## Twin fidelity per query (twin speedup / production speedup). Builds each configuration's
## indexes on pg-prod only while it measures and drops them, then proves pg-prod is back to
## primary key indexes only. Needs make seed. Writes sandbox.fidelity_path.
fidelity:
	$(TOOLS) python -m db.sandbox.fidelity
	$(TOOLS) python -m pytest -p no:cacheprovider -q db/tests/test_quickmart.py::test_only_primary_key_indexes

## Open the operator dashboard (bound to 127.0.0.1 only; never host it publicly).
demo:
	$(DC) up -d dashboard
	@echo "Operator dashboard: http://127.0.0.1:8501"
	-python -m webbrowser -t http://127.0.0.1:8501

## Drift demo (needs make seed): run the seeded mix, roll Q4 out over one drift window, then run
## the Q4-heavy mix. About 10 minutes with the demo window; watch the dashboard's drift panel.
drift-demo:
	$(TOOLS) python -m db.drift_demo

## End-to-end Q1 test (needs make up, make seed and GEMINI_API_KEY in .env). Writes runs/latest.json.
e2e:
	$(TOOLS) python -m pytest -p no:cacheprovider -v e2e

## Adversarial leak test on the payloads of the last passing e2e run (one live LLM call).
## Any other window: make adversarial SINCE=<iso time> UNTIL=<iso time>. Writes runs/adversarial.json.
adversarial:
	$(TOOLS) python -m privacy_tests.adversarial $(SINCE) $(UNTIL)

## Write site/results.json from the latest passing e2e run (refuses if there is none).
export:
	$(TOOLS) python -m scripts.export_results

## Build the public static site into site/dist (deploy that folder to Vercel).
site:
	$(TOOLS) python site/build.py

## Plan generation (GNN training data, step 18). Builds the bench image (DSB and TPC-H kits
## from pinned commits) and starts pg-bench. Loads dsb, tpch and a smaller QuickMart copy.
plans-load:
	$(DC) build pg-prod gateway
	$(DC) --profile bench up -d pg-bench
	$(DC) --profile bench build bench
	$(BENCH) python -m db.plangen load

## The early sample (plan_generation.early_sample_size runs) into data/plans/.
plans-sample:
	$(BENCH) python -m db.plangen sample

## Every template x parameter set x index setup, then dedupe. Resumable: rerun to continue.
plans:
	$(BENCH) python -m db.plangen run

## Rebuild data/plans/plans.jsonl and summary.json from plans_raw.jsonl.
plans-dedupe:
	$(BENCH) python -m db.plangen dedupe

## GNN training export (numbers only, may leave the machine) and split into data/gnn/.
gnn-export:
	$(BENCH) python -m db.plangen export

## The same export from the 200-plan sample (handoff H1 to the trainer).
gnn-export-sample:
	$(BENCH) python -m db.plangen export sample

## REFERENCE training loop (the trainer delivers the real weights) into models/gnn/weights/.
gnn-train-ref:
	$(TOOLS) python -m models.gnn.train

## Score the GNN weights and both baselines on unseen templates -> models/gnn/results.json.
gnn-eval:
	$(TOOLS) python -m models.gnn.evaluate

## Plan generation unit and component tests (component tests need make plans-load).
test-plangen:
	$(BENCH) python -m pytest -p no:cacheprovider db/plangen/tests

## Fast unit and contract tests, run in the tools container.
test:
	$(TOOLS) python -m pytest contracts/tests common/tests

## Data generation checks against the seeded pg-prod (run after make seed).
test-db:
	$(TOOLS) python -m pytest db/tests

## Gateway unit and component tests (component tests need make seed first).
test-gateway:
	$(TOOLS) python -m pytest gateway/tests

## Miner unit and component tests (component test needs make up and make seed).
test-miner:
	$(TOOLS) python -m pytest miner/tests

## Predictor tests (component test needs make up and make seed).
test-predictor:
	$(TOOLS) python -m pytest models/gnn/tests

## Greedy search, HypoPG and twin tests (component tests need make up and make seed).
test-search:
	$(TOOLS) python -m pytest rl/tests db/sandbox/tests db/twin/tests

## LLM agent tests that need no key (number checker, adapter, loop).
test-agent:
	$(TOOLS) python -m pytest agent/tests/test_agent.py agent/tests/test_ollama.py

## Live Gemini tests, run in the ai container (needs GEMINI_API_KEY in .env, then make up).
test-llm:
	$(DC) exec -T ai python -m pytest -p no:cacheprovider -rs agent/tests/test_live_llm.py

## Checksum verification on the twin (needs make up and make seed).
test-verify:
	$(TOOLS) python -m pytest verify/tests

## Dashboard tests (AppTest), run in the dashboard container (needs make up and make seed).
test-dashboard:
	$(DC) exec -T dashboard python -m pytest -p no:cacheprovider /app/dashboard/tests

## Every suite that runs in the tools container (component suites need make up and make seed).
test-all:
	$(TOOLS) python -m pytest -p no:cacheprovider contracts/tests common/tests db/tests gateway/tests miner/tests models/gnn/tests rl/tests db/sandbox/tests db/twin/tests agent/tests verify/tests scripts/tests privacy_tests/tests infra/tests/test_egress_proxy.py

## Exporter and site build tests (no services needed).
test-site:
	$(TOOLS) python -m pytest scripts/tests

## Network isolation and Postgres image tests, each in its own container.
test-infra:
	bash infra/tests/run.sh

## Air-gapped mode: recreate ai with the local model (Ollama on the host, llm.ollama.* in
## config.yaml) and no internet route. Needs Ollama listening on 10.31.31.1:11434 (README.md).
AIRGAP := $(DC) -f infra/docker-compose.airgap.yml
airgap:
	$(AIRGAP) up -d --no-deps ai

## Back to the default provider (Gemini): recreate ai from the base compose file.
online:
	$(DC) up -d --no-deps ai

## Air-gapped acceptance: isolation proof inside ai, then Q1 answered through the local model.
## The Q1 test skips only when ai cannot reach Ollama. Leaves ai in air-gapped mode.
test-airgap: airgap
	$(AIRGAP) exec -T -e PG_PROD_IP=$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $$($(DC) ps -q pg-prod)) \
		-e PG_TWIN_IP=$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $$($(DC) ps -q pg-twin)) \
		ai python -m pytest -p no:cacheprovider -rs -v infra/tests/test_airgap_network.py
	$(TOOLS) python -m pytest -p no:cacheprovider -rs -s infra/tests/test_airgap_q1.py
