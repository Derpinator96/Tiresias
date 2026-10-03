# models/gnn/: notes

Owner: Agent 3

Purpose: `predict(HashedPlan) -> Prediction`.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: SIMPLIFIED for the walking skeleton. Uses Postgres's own cost estimates, calibrated to ms at run time from a measured baseline plan. On-screen label: "estimator: Postgres cost x calibration (GNN pending)".

## Plug-in points not built yet

- GNN training and XGBoost baseline (MISSING).
