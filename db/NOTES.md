# db/: notes

Owner: Agent 1

Purpose: QuickMart schema and generator, canaries, Q1 runner, twin builder and sandbox (HypoPG and twin measurement).

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: `sales_rows` is 1,000,000 for now. regions 12, stores 500, products 50,000 are fixed; customers and returns scale with sales at ratio 0.04. All in config.yaml.
- 2026-10-03: sandbox code lives in `db/sandbox/`. The gateway imports it; it never runs in `ai`.
- 2026-10-03: twin parameter mapping by frequency rank. The twin replaces every most-common value from `pg_stats` with a synthetic value of the same type that keeps the original's frequency. A replayed query's filter value therefore has to be translated before it runs on the twin, or `region_id = 7` would hit a twin value with a different frequency. The mapping is built on the private side only: for each column, sort production's most-common values by frequency and the twin's synthetic values by the same frequencies, and pair them by rank. A production value of rank k maps to the twin value of rank k. Values outside the most-common list (numbers and dates sampled inside histogram buckets) are passed through unchanged, because bucket sampling keeps the same value range. The mapping is never sent across the boundary. To be implemented in step 10.

## Plug-in points not built yet

- DSB and TPC-H loaders (MISSING).
- Plan generation for GNN training (MISSING).
- Twin correlations for column pairs the miner flags (MISSING).
- pgbench write-cost scripts (MISSING).
- Q2 to Q4 (MISSING).
- 2026-10-03: Q1 measured after seeding at 1,000,000 sales rows: median 24.9 ms (runs 32.6, 24.5, 24.8, 24.9, 25.7), and 28.9 ms on a reseed. The doc's 500 ms auto_explain threshold would never log it. Proposed `workload.slow_query_ms: 10` (decision A), applied so the auto_explain path is exercised, pending human approval.
- 2026-10-03: Q1 matches 2,407 rows; region 7 holds 30.01% of sales; sales is 73 MB on disk.
- 2026-10-03: generation choices the doc leaves open, all in config.yaml: day weights grow linearly from 1 to `recent_density_ratio` (4.0); region is drawn first (hero at 30%, others uniform), then a store in that region; 20% of products (random choice) supply 80% of sales, so they earn about 80% of revenue; store opening dates, unit prices and quantities come from config ranges.
- 2026-10-03: canaries. 18 distinct values in db/canaries.py, 20 placements: 5 emails, 3 names, 2 phones, 3 sale amounts, 2 product names, 2 query comments, 2 filter queries (reusing a planted email and name), 1 DBA-question canary. Each has ID `cn_` plus the first 8 hex of SHA-256 of its value, so the ledger records hits without values.
- 2026-10-03: auto_explain plans are read from jsonlog lines whose `message` starts `duration: ... plan:` followed by the plan JSON. Each line also carries `query_id`, which equals pg_stat_statements' `queryid`; the gateway uses it to tie plans to templates.
- 2026-10-03: `make seed` drops and recreates every QuickMart table, then resets pg_stat_statements before running the workload, so stats reflect only the seeded workload.
