# Walking skeleton plan: query Q1 end to end

Goal: the thinnest version of the whole pipeline, wired through the real contracts, that answers
"Why is the weekly sales dashboard timing out?" for Q1 and measures the fix on the twin.

Source of truth: docs/architecture.md. Section names in quotes below refer to that doc.

## Decisions (approved 2026-10-03)

| # | Topic | Decision |
| --- | --- | --- |
| A | Q1 speed at `sales_rows: 1,000,000` vs the doc's 500 ms auto_explain threshold | Keep 1,000,000 rows. Add `slow_query_ms` to config.yaml; auto_explain's threshold and the e2e "Q1 is slow" check read it. Q1 is measured after seeding and a value is proposed for human approval. |
| B | Other table sizes | regions 12, stores 500, products 50,000 fixed. customers and returns scale with sales at ratio 0.04 (40,000 each at 1M sales). Ratios live in config.yaml. |
| C | LLM | Google Gemini API, a Flash model. The exact model name lives in config.yaml and is taken from the current model list, not guessed. Key in env var `GEMINI_API_KEY`. The LLM sits behind a provider adapter so provider and model are config values. HTTP 429 is retried with backoff, and the dashboard shows "rate limited, retrying" instead of failing silently. |
| D | Network isolation | `private` and `boundary` are `internal: true`. `ai` also joins an `egress` network with unrestricted internet, labelled SIMPLIFIED (allowlist proxy pending) everywhere it appears. `dashboard` joins an `operator` network with its port bound to 127.0.0.1 only. |
| E | No `make`, no host Python 3.11 | All Python runs inside the pinned 3.11 image. The Makefile only calls `docker compose`. The human installs GNU make (`winget install ezwinports.make`); the README lists the plain `docker compose` line for each target. |
| F | Em dashes and tool names in docs/architecture.md | Leave the doc unchanged; a cleaned version is coming from a human. |
| G | Git flow | One PR per build step, each branched from `main` after the previous PR merges. No stacking. Nothing is pushed to `main` directly. |
| H | ID formats | `plan_id` is `p_` plus 8 hex. `setup_id` is `s_` plus a lowercase slug. `cand_id`, `config_id`, `question_id` and `payload_id` are a prefix plus 8 hex. |
| I | Scanning LLM payloads | New endpoint `POST /v1/ledger/outbound`: `ai` submits each LLM request body, the gateway scans it, writes a `LedgerEntry` and returns allow or block. `ai` sends only on allow (fail closed). Added to contracts/ in step 2; the doc update comes from a human. |
| J | Vercel project | `blind-tuner`; if taken, `blind-tuner-demo`. |

Additional requirements:

1. e2e/test_q1.py fails, never skips, when `GEMINI_API_KEY` is missing.
2. results.json includes the git commit hash.
3. Step 3's hardcoded-literal test covers only modules and keys governed by config.yaml.
4. The twin's frequency-rank parameter mapping is documented in db/NOTES.md.

## Repository layout

```text
CLAUDE.md  PLAN.md  config.yaml  Makefile  README.md  .env.example
contracts/      schemas/*.schema.json, examples/, tests/
infra/          docker-compose.yml, postgres/ (Dockerfile, postgresql.conf), python/ (Dockerfile, requirements.in, requirements.lock), tests/
db/             schema.sql, generate.py, canaries.py, run_q1.py, twin/ (build.py), sandbox/ (hypopg.py, twin_measure.py), tests/
gateway/        hashing.py, strip.py, ingest/ (statements.py, plans.py, stats.py), rounding.py, ledger.py, canary_scan.py, resolver.py, dehash.py, api.py, tests/
miner/          fpgrowth.py, candidates.py, tests/
privacy_tests/  NOTES.md only (adversarial test and negative-control suite are out of scope)
models/gnn/     predictor.py (predict(HashedPlan) -> Prediction), tests/
rl/             search.py (run() -> Config), tests/
agent/          llm.py, tools.py, prompts.py, number_checker.py, api.py (/ai/*), tests/
verify/         checksum.py, tests/
dashboard/      app.py, plan_graph.py, .streamlit/config.toml, tests/
e2e/            test_q1.py, conftest.py
scripts/        export_results.py
site/           src/ (index, architecture, results, privacy, terms), favicon.svg, build.mjs, vercel.json
docs/           architecture.md
```

Every folder gets a NOTES.md. Sandbox code lives in `db/sandbox/` because the doc gives the twin to Agent 1 and puts the twin endpoints on the gateway. The gateway imports it, and it never runs in `ai`.

## Build order, files and tests

Each step ends by running its tests in Docker and pasting the output into the PR.

| # | Step | Main files | How it is tested |
| --- | --- | --- | --- |
| 1 | Layout, NOTES.md in each folder, README | folders above | `tree` output |
| 2 | Contracts: JSON Schema (draft 2020-12) for HashedQuery, HashedPlan, ColumnMeta, TableMeta, Candidate, Config, Prediction, SimResult, Rewrite, LedgerEntry and Answer. Code patterns are enforced: `^t_[0-9a-f]{8}$` and so on. | `contracts/schemas/`, `contracts/examples/` | pytest: every valid example passes, and every invalid example fails (a real name in `relation`, a literal in `sql`, a 4-hex code, a missing field). |
| 3 | config.yaml with every value from "Configuration values", plus `sales_rows: 1000000` and the defaults from decisions A and B | `config.yaml`, `common/config.py` (loader) | pytest: every key the code reads exists, and modules governed by config.yaml do not hardcode those keys' values. |
| 4 | Infra: Postgres 16 image with pg_stat_statements, auto_explain and HypoPG (PGDG apt package, pinned version). One Python 3.11 image with a `uv pip compile` lockfile. Services pg-prod, pg-twin, gateway, ai and dashboard; networks private, boundary, egress and operator (decision D). auto_explain uses jsonlog in a volume that only the gateway mounts read-only. | `infra/` | `infra/tests/test_isolation.py` runs inside `ai`: TCP connects to pg-prod:5432 and pg-twin:5432 must fail with a DNS or connection error, and the gateway must be reachable. A second test checks the extensions with `SELECT extname FROM pg_extension`. |
| 5 | QuickMart schema (primary and foreign keys only) and a generator following "Data generation rules": parents first; region 7 holds 30% of sales; 20% of products earn 80% of revenue; dates from 2024-01-01 to 2026-09-30, denser in recent months; sales carry their store's region_id; returns come 1 to 30 days after their sale. COPY, then ANALYZE. Canaries from "Canary placement": 5 emails, 3 names, 2 phones, 3 amounts, 2 product names, 2 commented queries, 2 queries filtering on a canary, and 1 question. `run_q1.py` runs Q1 N times (N in config). | `db/` | pytest against pg-prod: row counts match config; region 7's share is 30% plus or minus 1%; every sale's region equals its store's region; return gaps are 1 to 30 days; the index list holds only PK and FK indexes; every canary is present; Q1 appears in pg_stat_statements; Q1's plan appears in the auto_explain log. |
| 6 | Gateway (REAL): HMAC-SHA256 8-hex codes (`"table"` and `"table.column"`); sqlglot literal and comment stripping for SQL and for plan filter strings, failing closed with `filter_redacted`; alias resolution; ingestion from pg_stat_statements, the auto_explain jsonlog and pg_stats (skew = sum of the top 5 MCV frequencies only); rounding to 2 significant figures; the ledger (JSONL in a gateway volume); the canary scanner (case-insensitive, plus every 6-character fragment); the resolver (local name map to the top 3 templates); dehash; FastAPI endpoints for the Q1 flow (all of "Gateway API" except `/v1/approve`), plus `/v1/ledger/outbound` (decision I). | `gateway/` | Unit: same name gives the same code, the key changes the code, and table vs table.column differ; `7`, `'2026-09-26'` and `'Raipur'` become `?`; comments are removed; an unparsable filter is redacted; 49,812,334 rounds to 50,000,000; a planted canary and a 6-character fragment are both caught. Component: every endpoint response validates against its schema, and the canary scan of every response finds nothing. |
| 7 | Miner (REAL): baskets of `c_xxxxxxxx:ROLE` items per template, weighted by total_ms; mlxtend FP-Growth unweighted at a low threshold, then support recomputed as a share of total time and filtered at 5%; candidates ordered `=` columns, then ranges, then ORDER BY; at most 3 columns; leading column with at least 3 distinct values; drop candidates covered by an existing index; keep the top 30. | `miner/` | Unit: synthetic baskets with known weights give the expected support; ordering; covered-index pruning. Component: against the live gateway, the Q1 candidate is `[code(sales.region_id), code(sales.transaction_date)]` in that order. |
| 8 | Predictor (SIMPLIFIED): `predict(HashedPlan) -> Prediction` using Postgres's own estimates. ms per cost unit is calibrated at run time from the baseline auto_explain plan (actual ms divided by estimated cost), never hardcoded. Node shares are self cost over total cost. On-screen label: "estimator: Postgres cost x calibration (GNN pending)". | `models/gnn/` | Unit: output validates as Prediction, shares sum to 1, and the Seq Scan is the largest share for the Q1 baseline plan. |
| 9 | Search (SIMPLIFIED): `run() -> Config` greedy over the candidates. Each step adds the candidate with the best reward (the doc's formula with lambda_write and lambda_storage from config; write cost uses a per-index penalty, a new config value; storage uses HypoPG's estimated size) and stops when nothing improves. Scoring uses `/v1/simulate/hypopg` plus the predictor. Label: "search: greedy (RL pending)". | `rl/` | Component: the Config's first action is add_index on the Q1 candidate; a cached config is never re-costed. |
| 10 | Sandbox. HypoPG (REAL): create and EXPLAIN on one connection. Twin (SIMPLIFIED, no correlations): schema from `pg_dump --schema-only`; values from pg_stats only, with MCVs replaced by synthetic values of the same type and frequency and numbers and dates sampled inside histogram buckets; sales at 100% and the rest at 20%; ANALYZE afterwards. Q1 replays on the twin with its parameters mapped by frequency rank on the private side. Before and after are the median of 5 warm runs; storage in MB comes from `pg_relation_size`. | `db/twin/`, `db/sandbox/` | Twin: a canary scan of every twin text column finds nothing; the twin's Q1 plan operator sequence matches production's. Sandbox: SimResult validates; after_ms is below before_ms; storage_mb_delta is above 0. |
| 11 | LLM agent (REAL): tool calling with get_slow_templates, get_plan, mine_candidates, run_rl and simulate; system rules 1 to 7 from "LLM tools and system rules"; at most 8 tool calls; temperature 0; key from an environment variable (decision C). The number checker extracts every number outside hashed codes and requires each to match a tagged tool result, with one retry, then blocks. | `agent/` | Unit: the number checker passes a clean answer and blocks a planted invented number; code digits are ignored. Component: one live run returns a valid Answer. Needs `GEMINI_API_KEY`; the component test is skipped with a visible reason when it is absent, but e2e fails. |
| 12 | Verify (checksum only): MD5 of the sorted Q1 result rows on the twin, before and after the index (an index must not change the answer). | `verify/` | Component: the checksums match; a deliberately different query gives a mismatch. |
| 13 | Dashboard: question box; AI view / DBA view toggle; Graphviz plan tree; recommendation; twin before and after plus storage, with assumptions inline (for example "sales: 1,000,000 rows, not production size"); canary counter and negative-control button; a visible label on every simplified component. Streamlit branding, deploy button and default menu are removed using the options documented for the pinned version. Bound to 127.0.0.1. | `dashboard/` | Streamlit AppTest (if the pinned version ships `streamlit.testing`; checked then) renders every panel and finds each SIMPLIFIED label; a screenshot is attached to the PR. |
| 14 | e2e/test_q1.py: the whole Q1 flow. Asserts Q1 is slow before the fix (threshold from config, decision A); the recommendation is the region_id and transaction_date codes in that order; the twin speedup is over 50%; there are zero canary hits across the ledger; every number in the answer traces to a tool result. | `e2e/` | `make e2e` under 2 minutes (seeding happens beforehand, in `make seed`). |
| 15 | Export and site: `export_results.py` writes results.json (run ID, timestamp, dataset size, each number with its assumption) from the latest e2e run, plus the git commit hash. Static site with five pages (what it does, architecture, results, privacy, terms), a real favicon, no database access, and no real names or raw values. A build script renders results.json into the results page. The privacy policy and terms are flagged for your review. | `scripts/`, `site/` | A test checks that results.json validates, that the site's built HTML contains no real table or column name and no canary, and that all five pages and the favicon exist in `dist/`. |
| 16 | Makefile: up, seed, e2e, demo, export, site | `Makefile` | Run every target from a fresh clone. |

## Out of scope this session (left as MISSING with a TODO at the plug-in point)

DSB and TPC-H loading, GNN training, Q-learning, Q2 to Q4, partitioning, drift, the adversarial leak test, air-gapped mode, VeriEQL, approve and migration scripts, twin correlations, the tools gnn_explain, rewrite_candidates and verify, RAG over R-Bot rules, and the egress allowlist proxy.

## Commands you run yourself

- Put the LLM API key and the HMAC key in `.env` (I generate a template; the HMAC key comes from `make keygen`, which writes it to `.env` without printing it).
- `npm i -g vercel`, `vercel login`, then the deploy commands I give you at the end.
- Install GNU make (decision E).
