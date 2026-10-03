# rl/: notes

Owner: Agent 3

Purpose: `run() -> Config`.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: SIMPLIFIED for the walking skeleton. Greedy search over miner candidates, scored with HypoPG plus the predictor. On-screen label: "search: greedy (RL pending)".

## Plug-in points not built yet

- Tabular Q-learning: built in step 20.
- Partition and rewrite actions (MISSING).
- 2026-10-03: `rl.lambda_storage` changed from the doc's 1.0 to 0.25, approved by a human. With the doc's values the reward rejected the Q1 index (predicted drop 0.641, storage term 1.179 for a 28 MB index against a 23.8 MB budget, write term 0.100, reward -0.638), contradicting the RL acceptance criterion. The formula and the 25% budget are unchanged.
- 2026-10-03: the doc's reward subtracts lambda_write x write ms (milliseconds) from a unitless fractional drop. Kept as is, approved by a human: with `write_penalty_ms_per_index` 0.1 it acts as a flat 0.1 per index and is labelled as an assumption. Fix the units once pgbench measures write cost.
- 2026-10-03: workload time W = sum over slow templates of (share of calls) x predicted total ms of the template's HypoPG plan. Baseline W is also predicted from an estimated plan (empty config), so before and after use the same estimator.
- 2026-10-03: live result: baseline 28.573 ms predicted, Q1 composite 10.253 ms predicted, reward 0.2464; the date-only index adds nothing after it, so the search stops at one action. 6 configs costed.
- 2026-10-03: `/ai/rl/run` returns the Config plus the trace (steps, rewards, predicted ms, configs costed, cache hits) and both on-screen labels.
- 2026-10-03: step 20, tabular Q-learning (QLearningSearch) per the doc: state = chosen set, actions = remaining candidates or stop, epsilon-greedy with linear decay from rl.epsilon_start to rl.epsilon_min, rl.episodes episodes of up to rl.actions_per_episode actions, the same reward and cost cache as greedy. Config.search is "q_learning".
- 2026-10-03: two algorithm choices beyond the doc's text, both made after a failing test (overlapping indexes: X best alone, Y plus Z best together). With Q starting at 0 and doc epsilon 0.1 to 0.02, X was tried first, looked good, and Y was rarely explored, so the agent ended on X, Y, Z. Fixes: optimistic initial Q (`rl.q_init: 1.0`, not in the doc's table) so every option is tried; and the final Config is the visited configuration with the highest total reward (the doc's "re-score the top configurations"), not a rollout of possibly under-learned Q-values.
- 2026-10-03: the Q-table lives in the ai process and persists across /ai/rl/run calls, so new template weights continue learning (doc: on drift, do not restart). Drift detection itself is still MISSING in the miner; test_adapts_to_new_weights_without_restarting shows the mechanism with changed weights.
- 2026-10-03: run() also runs greedy on the same cost cache and returns it as `greedy` (doc: compare RL with greedy). Live Q1 at 10,000,000 rows: Q-learning and greedy pick the same index (predicted 120.0 ms to 39.3 ms), 300 episodes in about 2 s, 8 configurations costed, 456 cache hits. With one dominant candidate they tie, which the doc says to state plainly; the overlap test shows a case where Q-learning wins.
- 2026-10-03: SIMPLIFIED, label "search: Q-learning, index actions only (rewrite, partition and top-3 twin re-check pending)". The top 3 configurations are listed in the trace, but only the chosen one is measured on the twin.
- 2026-10-03: write cost is now measured on the twin for the chosen configuration (step 24, db/sandbox/write_cost.py). The search keeps the per-index penalty during search (doc: "use a simple per-index penalty in search; measure the final choice on the twin"). Measured for the Q1 index: median 0.032 ms per insert over 6 runs (db/NOTES.md), below the assumed `write_penalty_ms_per_index` 0.1. Not changed: changing it or rescaling lambda_write's units needs a human.
