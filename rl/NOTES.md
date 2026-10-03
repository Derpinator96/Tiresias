# rl/: notes

Owner: Agent 3

Purpose: `run() -> Config`.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: SIMPLIFIED for the walking skeleton. Greedy search over miner candidates, scored with HypoPG plus the predictor. On-screen label: "search: greedy (RL pending)".

## Plug-in points not built yet

- Tabular Q-learning (MISSING).
- Partition and rewrite actions (MISSING).
- 2026-10-03: `rl.lambda_storage` changed from the doc's 1.0 to 0.25, approved by a human. With the doc's values the reward rejected the Q1 index (predicted drop 0.641, storage term 1.179 for a 28 MB index against a 23.8 MB budget, write term 0.100, reward -0.638), contradicting the RL acceptance criterion. The formula and the 25% budget are unchanged.
- 2026-10-03: the doc's reward subtracts lambda_write x write ms (milliseconds) from a unitless fractional drop. Kept as is, approved by a human: with `write_penalty_ms_per_index` 0.1 it acts as a flat 0.1 per index and is labelled as an assumption. Fix the units once pgbench measures write cost.
- 2026-10-03: workload time W = sum over slow templates of (share of calls) x predicted total ms of the template's HypoPG plan. Baseline W is also predicted from an estimated plan (empty config), so before and after use the same estimator.
- 2026-10-03: live result: baseline 28.573 ms predicted, Q1 composite 10.253 ms predicted, reward 0.2464; the date-only index adds nothing after it, so the search stops at one action. 6 configs costed.
- 2026-10-03: `/ai/rl/run` returns the Config plus the trace (steps, rewards, predicted ms, configs costed, cache hits) and both on-screen labels.
