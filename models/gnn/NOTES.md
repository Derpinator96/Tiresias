# models/gnn/: notes

Owner: Agent 3

Purpose: `predict(HashedPlan) -> Prediction`.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: SIMPLIFIED for the walking skeleton. Uses Postgres's own cost estimates, calibrated to ms at run time from a measured baseline plan. On-screen label: "estimator: Postgres cost x calibration (GNN pending)".

## Plug-in points not built yet

- GNN training and XGBoost baseline (MISSING).
- 2026-10-03: `CostPredictor.fit(measured_plans)` computes ms_per_cost = sum of measured self_ms / sum of root est_cost over plans that ran. `/ai/gnn/predict` calibrates on auto_explain plans in the request, else fetches the gateway's measured plans for the same templates. A plan set with no measurement returns HTTP 409, never a guess.
- 2026-10-03: node self cost = node est_cost minus its children's est_cost (Postgres costs are cumulative), clamped at 0. Share = self cost / sum of self costs.
- 2026-10-03: measured effect of gateway rounding: Q1's est_cost values arrive as 17000, 17000, 16000, 16000 (2 significant figures), so node shares are coarse (Seq Scan 0.94, Gather 0.06, aggregates 0). The Seq Scan is still clearly the bottleneck.
- 2026-10-03: weakness, stated on screen: one ratio calibrated on a sequential scan is applied to index plans, and Postgres cost units do not scale equally across operators. Twin measurements, not predictions, are the numbers shown as results.
