# Blind Tuner. Every target only calls docker compose; all Python runs in the pinned image.
# Targets are added step by step; see PLAN.md. The README lists the plain docker compose
# line for each target, for machines without make.

export MSYS_NO_PATHCONV := 1
DC := docker compose -f infra/docker-compose.yml --project-directory .
TOOLS := $(DC) run --rm -T tools

.PHONY: keygen up down seed twin test test-agent test-llm test-infra test-db test-gateway test-miner test-predictor test-search

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
	$(TOOLS) python -m pytest agent/tests/test_agent.py

## Live Gemini tests, run in the ai container (needs GEMINI_API_KEY in .env, then make up).
test-llm:
	$(DC) exec -T ai python -m pytest -p no:cacheprovider -rs agent/tests/test_live_llm.py

## Network isolation and Postgres image tests, each in its own container.
test-infra:
	bash infra/tests/run.sh
