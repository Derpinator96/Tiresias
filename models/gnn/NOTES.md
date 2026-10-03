# models/gnn/: notes

Owner: Agent 3

Purpose: `predict(HashedPlan) -> Prediction`, the GNN's features, architecture, reference training and scoring.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: SIMPLIFIED for the walking skeleton. Uses Postgres's own cost estimates, calibrated to ms at run time from a measured baseline plan. On-screen label: "estimator: Postgres cost x calibration (GNN pending)".

## Plug-in points not built yet

- GNN training and XGBoost baseline (MISSING).
- 2026-10-03: `CostPredictor.fit(measured_plans)` computes ms_per_cost = sum of measured self_ms / sum of root est_cost over plans that ran. `/ai/gnn/predict` calibrates on auto_explain plans in the request, else fetches the gateway's measured plans for the same templates. A plan set with no measurement returns HTTP 409, never a guess.
- 2026-10-03: node self cost = node est_cost minus its children's est_cost (Postgres costs are cumulative), clamped at 0. Share = self cost / sum of self costs.
- 2026-10-03: measured effect of gateway rounding: Q1's est_cost values arrive as 17000, 17000, 16000, 16000 (2 significant figures), so node shares are coarse (Seq Scan 0.94, Gather 0.06, aggregates 0). The Seq Scan is still clearly the bottleneck.
- 2026-10-03: weakness, stated on screen: one ratio calibrated on a sequential scan is applied to index plans, and Postgres cost units do not scale equally across operators. Twin measurements, not predictions, are the numbers shown as results.
- 2026-10-03: GNN track (step 19). A human decided: someone else trains the model (Colab or another machine); this repo owns the features, the split, the architecture and the scoring. The trainer returns `weights/gnn.pt` (a PlanGNN state_dict) and `weights/meta.json` (feature_version, n_features, hidden_size, layers, dropout, trained_on_plans).
- 2026-10-03: features (`features.py`, FEATURE_VERSION 1) are computed from HashedPlan nodes through `strip()`, by export, training, evaluation and serving alike, so train and serve features match (db/plangen/tests/test_export.py::test_features_match_serving_path). Deviation from the doc, approved by a human 2026-10-03: no role bits and no table rows, because HashedPlan nodes do not carry them.
- 2026-10-03: `model.py` is plain PyTorch (no PyTorch Geometric): single-head attention over each node and its children, 3 layers, hidden 128, dropout 0.1, residual connections, output log1p(self_ms) per node. Doc's spec except the head count, which the doc leaves open. test_gnn.py checks that batching never mixes graphs.
- 2026-10-03: `train.py` is a REFERENCE loop (doc's optimiser settings from config gnn.*); it proves the handoff end to end. Not the delivered model.
- 2026-10-03: `evaluate.py` scores every predictor on split.json's test templates: median and p95 q-error of total runtime, pairwise ranking accuracy across index setups, bottleneck match. Baselines: the existing CostPredictor fit on the training split, and scikit-learn HistGradientBoosting standing in for XGBoost (human decision 2026-10-03). Timed-out plans are counted, not scored.
- 2026-10-03: serving. `load_predictor()` returns GNNPredictor only when results.json shows its median q-error below the Postgres baseline's; otherwise CostPredictor. Its label carries the scored median q-error and names results.json. `/ai/gnn/estimator` tells the dashboard which estimator serves, so every label names the real one.
- 2026-10-03: torch 2.11.0+cpu lives in infra/python/requirements-ml.lock, installed as its own image layer (constrained by requirements.lock) so adding it did not re-download every other package on a slow network.
