# gateway/: notes

Owner: Agent 2

Purpose: HMAC hashing, literal stripping, ingestion, rounding, payload ledger, canary scanner, question resolver, dehash and the gateway API.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: the HMAC key is read from the uncommitted `.env` only. Never print, log or commit it.

## Plug-in points not built yet

- `POST /v1/approve` with migration and rollback scripts (MISSING).
- 2026-10-03: sqlglot 30.21.0 behaviour, checked in the pinned image: `$1` parses as Parameter(Literal 1), so the whole Parameter is replaced; `comments=False` drops `/* */` and `--` comments; the postgres dialect renders a Placeholder as `%s`, so hashed SQL is rendered in the generic dialect, which prints `?`.
- 2026-10-03: fail closed (strip.py raises Unparsed, nothing is sent) when: the SQL does not parse; a table is not a QuickMart table (this also drops catalog queries); a column is ambiguous or unknown; any identifier other than a code survives (this closes the uppercase-identifier gap noted in contracts/NOTES.md); the output does not match the contract's hashed_sql pattern. Output column aliases are removed; subquery aliases fail closed.
- 2026-10-03: plan conditions (Filter, Index Cond, Recheck Cond, Join Filter, Hash Cond, Merge Cond) are hashed one by one. One that fails is dropped and the node is marked `filter_redacted`.
- 2026-10-03: template codes are HMAC of pg_stat_statements' normalized text, not of queryid: queryid depends on table OIDs and changes on every reseed. Plans join templates through jsonlog `query_id` = pg_stat_statements `queryid`.
- 2026-10-03: only queries of `workload.app_role` (quickmart_app) are ingested, so test and catalog queries never become templates. db/seed.py creates the role.
- 2026-10-03: self time per plan node = total minus children. For nodes under Gather, or Parallel Aware nodes, per-loop time is used as wall time (workers overlap); otherwise time is multiplied by loops. Negative results clamp to 0.
- 2026-10-03: rounding to 2 significant figures applies to row counts, distinct counts, est_rows, est_cost, table rows and sizes. Times (mean_ms, total_ms, self_ms) are not counts or sizes and are rounded to 0.1 ms or 0.001 ms only.
- 2026-10-03: `TableMeta.writes_per_s` is measured (row writes since the stats reset, per second), but there is no steady write workload yet, so after `make seed` it mostly reflects the seed's bulk COPY. pgbench is pending.
- 2026-10-03: every AI-facing response goes through `Gateway.send_to_ai`: contract validation, canary scan, ledger entry. A hit blocks the response with HTTP 403. The ledger logs what the AI side receives (responses), and LLM request bodies via `/v1/ledger/outbound`; requests from ai to the gateway carry only codes and are not ledgered.
- 2026-10-03: the scanner also matches 6-character fragments. The planted emails share fragments (`@corp.`, `ANARY_`), so one leaked email produces several hits in one entry. Counters report payloads blocked and hits separately.
- 2026-10-03: the negative control scans raw pg_stat_statements texts and raw auto_explain plans (what would leave with the gateway off). It goes to the local scanner only; the two comment canaries are what it finds.
- 2026-10-03: the question resolver uses `gateway/resolver_map.yaml` (private, real names) plus table-name matching. The question text is never ledgered or sent; the response says whether it held a canary.
