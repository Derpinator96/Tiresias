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
- 2026-10-03: `db/sandbox/hypopg.py` (REAL). Creates hypothetical indexes and runs every EXPLAIN on one connection, with hypopg_reset() before and after. Size from hypopg_relation_size. A template without a logged literal query is planned with EXPLAIN (GENERIC_PLAN), new in PostgreSQL 16. Checked against HypoPG 1.4.3.
- 2026-10-03: twin (SIMPLIFIED, no correlations) in `db/twin/build.py`. Schema from `pg_dump --schema-only --clean --if-exists --no-owner --no-privileges`, run inside pg-twin (it has pg_dump 16; the Python image has no pg_dump). Values from pg-prod's pg_stats: primary keys 1..n; foreign keys by frequency rank onto parent IDs 1..k, remaining mass over the other parent IDs; numeric and date most-common values replaced by a value sampled between their neighbours in the sorted list of known values; the rest sampled uniformly inside equi-depth histogram buckets; text most-common values replaced by synthetic strings of the same length; other text synthetic; NULLs at null_frac. Text histograms are never used: the first `customers.email` histogram bound is the planted canary CANARY_7731@corp.com.
- 2026-10-03: twin sizes: sales at 100%; other tables at 20% but never below the distinct count a child's foreign key needs. Result: customers 38,660, products 19,113 (pg_stats' n_distinct estimate for sales.product_id), regions 12, stores 500, sales 1,000,000, returns 8,000.
- 2026-10-03: the frequency-rank map is written to `sandbox.twin_map_path` in the gateway's volume (mounted by gateway and tools, never by ai). Real region 7 (rank 1) maps to twin region 1.
- 2026-10-03: base tables only. information_schema.columns also lists the views HypoPG and pg_stat_statements install in `public`; the twin builder and the gateway catalog both filter to BASE TABLE.
- 2026-10-03: twin measurement (`db/sandbox/twin_measure.py`): equality literals translated with the rank map (range literals unchanged); plan agreement compares preorder Node Type sequences of EXPLAIN on prod and twin; median of 5 timed runs after 1 warm-up; indexes built for real on the twin, sized with pg_relation_size, then dropped.
- 2026-10-03: measured Q1 on the twin: 24.297 ms before, 2.662 ms after (89% faster); plans agree; real index 6.8 MB against HypoPG's 28 MB estimate (unverified cause; B-tree deduplication of repeated region_id values is the likely reason).
- 2026-10-03: canary check for dense numbers. The twin draws 1,000,000 amounts at cent precision (540,068 distinct), so any cent value appears by chance about as often as its neighbours: 9953.99 appeared once, with 3 of its 10 neighbouring cent values present; 7731.77 had 6 of 10 neighbours present. A row-level exact match cannot tell a leak from chance, so the test checks that no canary amount is an input the generator copies or anchors on (the rank map, the histogram bounds). Text columns are scanned for exact canaries and 6-character fragments and find nothing. Flagged for a human: the doc's "canary scan of the twin finds nothing" needs this reading for numeric canaries.
- 2026-10-03: canary values changed after the first live LLM run was blocked: the comment canaries held the English word COMMENT, and the scanner's 6-character fragment `commen` matched "recommended" in the agent's own system prompt. Comment canaries are now CANARY_QXZ7731_VK and CANARY_QXZ7732_VK; the name Corvin Halloweth (fragment `allowe`, as in "allowed") is now Corvin Hzalweth. db/tests/test_canaries.py checks every fragment against the agent's prompts and tool declarations and against the architecture doc's English (with the doc's own canary examples removed). Reseed after changing canaries.
