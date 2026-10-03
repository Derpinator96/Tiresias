# contracts/: notes

Owner: humans (frozen; agents edit only with human approval)

Purpose: JSON Schemas for every hand-off in the doc's "Interface contracts", plus contract tests.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: ID formats. Codes crossing the boundary are `t_`, `c_`, `i_`, `q_` plus 8 hex. `plan_id` is `p_` plus 8 hex. `setup_id` is `s_` plus a lowercase slug. `cand_id`, `config_id`, `question_id` and `payload_id` are a prefix plus 8 hex.
- 2026-10-03: approved addition `POST /v1/ledger/outbound`. `ai` submits each LLM request body; the gateway scans it, writes a `LedgerEntry` and returns allow or block. `ai` sends only on allow (fail closed). The doc's API table will be updated by a human.
