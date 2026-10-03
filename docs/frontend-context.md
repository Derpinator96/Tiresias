# Blind Tuner: context for front-end work

Snapshot 2026-10-04, main 539e395. Source of truth is docs/architecture.md; if this file and the code disagree, ask a human.

## What it is
Blind Tuner (CodeUtsava X.0, PS4): an AI that finds fixes for slow PostgreSQL queries while seeing only disguised metadata, and proves both the privacy and the speedup. Pitch: "We prove the AI never saw your data, and we prove every change works before you apply it."

## Demo case
QuickMart retail schema (our own): sales 10,000,000 rows, regions 12, stores 500, products 50,000, customers 400,000, returns 400,000. Hero query Q1: `SELECT SUM(amount) FROM sales WHERE region_id = 7 AND transaction_date >= '2026-09-26'`. Fix: composite index (region_id, transaction_date), equality column first. Region 7 holds 30.01% of sales rows (skew).

## Pipeline (the 9 UI steps)
Dataset, Slow Query, Privacy Gateway, Pattern Miner, GNN, RL, LLM, Twin Sandbox, DBA Console.
1. Postgres logs the slow template (pg_stat_statements, auto_explain; slow_query_ms 100).
2. The gateway is the only door to the AI zone: HMAC-SHA256 hashing of names, sqlglot literal stripping, bitmask column roles, pg_stats redaction, canary scan of every outgoing payload, payload ledger.
3. FP-Growth miner proposes index candidates weighted by calls x latency; drift by Jensen-Shannon distance (2-window trigger).
4. Cost estimator: today Postgres cost x calibration, labelled "estimator: Postgres cost x calibration (GNN pending)". The GNN pipeline is built; trained weights are not delivered.
5. Tabular Q-learning over index, rewrite and partition actions; top 3 re-checked on the twin; best measured wins.
6. LLM agent (Gemini; Ollama air-gapped mode plumbed, real model unverified) with 8 tools; a number checker verifies every number it states.
7. Statistical twin (synthetic rows from pg_stats) measures before and after, index MB, write cost (pgbench), plan agreement, result checksum; HypoPG for what-if.
8. DBA approves: /v1/approve returns migration.sql (CREATE INDEX CONCURRENTLY), rollback.sql and a post-deploy check that reverts if latency worsens. It refuses the ai service (403).

## Trust boundary
Docker networks: `private` (pg-prod, pg-twin, gateway, dashboard; no internet) and `boundary` (gateway, ai, dashboard, optional ollama). Only `ai` reaches the internet, through a CONNECT-only allowlist proxy to the LLM host. VeriEQL runs in its own image (CC BY-NC-SA 4.0, replace before commercial use).

## APIs
Gateway: /v1/templates/slow, /v1/templates/{id}/plans, /v1/meta/*, /v1/simulate/hypopg and /twin, /v1/twin/checksum, /v1/twin/fidelity, /v1/ask/resolve, /v1/answers/dehash, /v1/ledger, /v1/privacy/negative-control, /v1/rewrite/candidates and /verify, /v1/approve, /v1/approve/twin-check, /v1/withheld.
AI: /ai/mine, /ai/gnn/predict, /ai/gnn/explain, /ai/rl/run, /ai/ask, /ai/llm.
Contracts: JSON Schemas in contracts/ (HashedQuery, HashedPlan, ColumnMeta, TableMeta, Candidate, Config, Prediction, SimResult, Rewrite, LedgerEntry, Answer, OutboundPayload).

## Real numbers (run_d1b30d38, 2026-10-03)
- Q1 mean 183.9 ms on prod at 10M rows.
- Twin: 303.6 to 98.3 ms, 67.6% faster, median of 5 runs; index 68 MB; checksum match; +0.03 ms per insert.
- Search predicted 120.0 to 39.3 ms.
- 43 payloads sent, 5 to the LLM, 0 canary hits of 20 planted.
- 5 LLM tool calls, 4 numbers checked.
- Q2 rewrite 63.5% faster, 78.2% with an index; on the correlated twin Q2 measures 22% to 45% (at risk against the PS4 target).
- Q3 partition 217.8 to 46.2 ms on the twin.
- Twin fidelity: Q1 0.76, Q2 0.99, two-region 0.95.
- GNN reference loop, 40 test plans: GNN 2.47, Postgres 2.54, GBT 1.56 median q-error (too small to conclude).

Not done: adversarial leak test live score, trained GNN, real air-gapped model, drop-index action, public deploy, privacy and terms human review. See to-do.md.

## Existing UIs
- dashboard/: Streamlit operator dashboard, local only, two pages (Ask, Details). Shows real names, never hosted publicly.
- site/: public static site, 5 pages plus favicon, built by site/build.py, not deployed. site/results.json is run_9247c060 (1M rows) and is stale against run_d1b30d38.
- site/web/: empty Next.js, Tailwind and shadcn scaffold for the new front end (see site/web/NOTES.md).

## Hard rules for any front end (CLAUDE.md)
- No purple gradients, no pill-shaped buttons, no emoji icons, no scroll animation, parallax or custom cursors, no AI imagery.
- No em dashes anywhere. Headings state a fact or name a function. No filler copy.
- No fabricated reviews, logos or metrics. Every number traces to a real computation, with its assumption beside it. Placeholders are visibly labelled. Simplified components are labelled on screen.
- Ship gates: clean URL, favicon, no builder badge, privacy page, terms page.
- Only the static site is public. Every tunable lives in config.yaml. The HMAC key lives only in an uncommitted .env.

## Inspiration brief
Evidence-first developer-tool SaaS: query observability (Datadog DBM, pganalyze, PlanetScale Insights), approval and audit consoles, stepper pipelines, plan-tree viewers (explain.dalibo.com). Wanted: dense calm tables, a visible trust-boundary diagram, before and after cards with assumption captions, diff-style SQL viewers, audit ledger views.
