# miner/: notes

Owner: Agent 2

Purpose: FP-Growth with weighted support, producing index candidates.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- None yet.

## Plug-in points not built yet

- Template clustering beyond queryid (MISSING). Drift detection: built in step 25 (miner/drift.py).
- 2026-10-03: REAL FP-Growth (mlxtend 0.25.0). Baskets hold `column:ROLE` for EQ, JOIN, RANGE, ORDER and GROUP (SELECT is not an index signal), weighted by total_ms. FP-Growth runs unweighted at `miner.unweighted_min_support`, then support is recomputed as share of total time and filtered at `miner.min_weighted_support`.
- 2026-10-03: candidate column order: EQ, then JOIN, then RANGE, then ORDER; ties by higher n_distinct, then code. GROUP items never enter a candidate. Itemsets spanning two tables are skipped. The leading column needs `miner.min_leading_distinct` distinct values.
- 2026-10-03: SIMPLIFIED covered-index check. ColumnMeta says only whether a column is indexed, not which composite index holds it, so `/ai/mine` treats each primary key column as a one-column index. A candidate is covered when an existing index on the same table starts with exactly its columns.
- 2026-10-03: ranking: support descending, then more columns first, so the composite (region_id, transaction_date) outranks its single-column subsets at equal support.
- 2026-10-03: `/ai/mine` returned `drift: {state: MISSING}` in the walking skeleton; superseded by step 25 (miner/drift.py).
- 2026-10-03: the component test runs in the tools container, calls the miner on live gateway data, and translates the winning codes through `/v1/answers/dehash`. The miner itself never sees a real name.
- 2026-10-03: human-approved test change: with Q2 in the workload (step 21) Q2 holds about 70% of slow time and its candidates rank first. miner/tests/test_q1_candidate.py now finds Q1's composite by real name (must be region then date, never reversed, support >= 0.05) instead of taking the first composite; db/sandbox/tests/test_hypopg.py measures Q1's template by its query text, as e2e/test_q1.py does.
- 2026-10-03: step 23, rewritten shapes. `with_rewritten_shapes(templates, rewrites)` adds to each template's columns the roles of its rewritten shapes, from the gateway's rewrite candidates (codes and roles only, computed privately by hash_sql on the real rewritten query). A rule that unwraps a column (date_trunc(c) = ? becomes a range on c) gives c a role, so an index that only helps after the rewrite is mined: on the live stack, (store_id, transaction_date) for Q2. Each template still counts its time once (the extra roles join its own basket), so support stays a share of real query time. Effect on ranking: sales (transaction_date) now has support 1.0 (Q2 has it after its rewrite); stores (region_id, store_id) stays the top composite, so test_q1_candidate fails as before (pre-existing since step 21, being fixed on the base branch).
- 2026-10-03: step 25, drift (miner/drift.py, REAL per the doc). Per window, each template's share of total time; Jensen-Shannon distance between consecutive windows with scipy's jensenshannon at base 2 (0 = same mix, 1 = disjoint), which returns the distance; the doc's 0.2 applies to the distance ("Jensen-Shannon distance above 0.2 for 2 windows"). Drift triggers when the distance is above `miner.drift_js_threshold` for `miner.drift_windows_required` windows in a row. Windows with no queries carry no mix and are skipped. `triggered` stays true while the window that completed the trigger is among the `miner.drift_windows_kept` windows the gateway returns. The new weights for the search are the latest window's call shares (doc, Component 4: state includes how often each template runs).
- 2026-10-03: `/ai/mine` returns `{candidates, label, drift}`; `label` is the covered-index simplification ("miner: covered-index check knows primary keys only"). Body `{"window_s": n}` is a test-only override of the drift window; the configured window (`miner.drift_window_mode` demo, 120 s) is what the demo uses.
- 2026-10-03: FLAGGED FOR A HUMAN, doc rule: comparing consecutive windows means a sudden permanent switch gives one large distance, then the new mix compares equal to itself, so it never stays above the threshold for 2 windows unless the switch lands inside a window (miner/tests/test_drift.py::test_doc_rule_misses_a_sudden_switch_on_a_window_boundary documents it). `make drift-demo` rolls Q4 out over one window, which triggers at any alignment (test_rollout_over_one_window_triggers_at_any_alignment: offsets 0 to 0.99 of a window, trigger at most 2 windows after the rollout ends). Proposed change, not made: compare each window with the window the last tuning used, which catches a step switch at any alignment.
- 2026-10-03: live component test (miner/tests/test_drift_live.py, 15 s test window, start aligned to a window boundary): distances 0.0206 between the two windows of the seeded mix, then 0.3937 and 0.4413 after the switch began; drift triggered at the second window after the switch began. The search in the running ai process then moved from (region_id, transaction_date) to (transaction_date), which Q4's HypoPG plan uses.
