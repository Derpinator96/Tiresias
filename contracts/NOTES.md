# contracts/: notes

Owner: humans (frozen; agents edit only with human approval)

Purpose: JSON Schemas for every hand-off in the doc's "Interface contracts", plus contract tests.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: ID formats. Codes crossing the boundary are `t_`, `c_`, `i_`, `q_` plus 8 hex. `plan_id` is `p_` plus 8 hex. `setup_id` is `s_` plus a lowercase slug. `cand_id`, `config_id`, `question_id` and `payload_id` are a prefix plus 8 hex.
- 2026-10-03: approved addition `POST /v1/ledger/outbound`. `ai` submits each LLM request body; the gateway scans it, writes a `LedgerEntry` and returns allow or block. `ai` sends only on allow (fail closed). The doc's API table will be updated by a human.
- 2026-10-03: ID prefixes chosen for decision H: `cand_`, `cfg_`, `qn_` (question), `pay_` (payload), `rw_` (rewrite), `tc_` (tool call), `cn_` (canary), each plus 8 hex.
- 2026-10-03: fields added beyond the doc's key-field list, each so that a simplification can be labelled or a leak blocked:
  - `HashedPlan.nodes[]`: `index` (index code), `filter` (hashed filter expression), `filter_redacted` (fail closed).
  - `HashedPlan`: plans with source `explain` or `hypopg` may not carry `actual_rows`, `rows_removed` or `self_ms` (the doc's rule, enforced by the schema).
  - `Prediction.estimator` and `Config.actions[].contribution.estimator`: `postgres_cost_calibrated` or `gnn`, so the dashboard can label the SIMPLIFIED estimator.
  - `Config.search`: `greedy` or `q_learning`, so the dashboard can label the SIMPLIFIED search.
  - `Config.actions[].contribution`: the doc asks for each action's contribution; it is optional per action.
  - `Candidate.evidence`: structured (`items`, `templates`) instead of free text, so no free text crosses the boundary.
  - `LedgerEntry.canary_hits[]`: `{canary_id, match}`; the canary value itself is never stored in the ledger. `verdict`: allow or block.
  - `SimResult.write_ms_delta`: required but nullable; null means write cost was not measured (pgbench is out of scope this session).
  - `OutboundPayload`: request body of `POST /v1/ledger/outbound` (decision I); the response is a `LedgerEntry`.
- 2026-10-03: `hashed_sql` pattern. Outside codes, only uppercase keywords, operators, punctuation and `?` are allowed; no lowercase word, digit, quote or `$`; no comments. Limitation: an unquoted uppercase identifier looks like a keyword to the schema, so the gateway's own tests must cover identifiers.
- 2026-10-03: `plan_node_type` enum is the 42 `sname` values from PostgreSQL REL_16_STABLE `src/backend/commands/explain.c`, which is what EXPLAIN (FORMAT JSON) writes as "Node Type".
- 2026-10-03: example codes in `examples/` are illustrative, not real HMAC output.

## How to run the contract tests

Until step 4 adds the shared image, from the repo root (Git Bash needs `MSYS_NO_PATHCONV=1`):

```bash
docker run --rm -v "$PWD:/repo" -w /repo python:3.11.17-slim sh -c "pip install -q -r contracts/requirements-test.txt && python -m pytest contracts/tests"
```

## Layout

- `schemas/`: one JSON Schema (draft 2020-12) per contract, plus `common.schema.json` for shared code formats.
- `examples/valid/<Name>.json`: instances that must pass. `examples/invalid/<Name>.json`: `{why, instance}` pairs that must fail.
- `validate.py`: `validate(name, obj)` and `errors(name, obj)` for every other component.
