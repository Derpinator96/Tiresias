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
