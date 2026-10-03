# verify/: notes

Owner: Agent 4

Purpose: Result checksums on the twin; VeriEQL later.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: checksum only for now. Compares Q1's sorted result rows on the twin before and after the index.

## Plug-in points not built yet

- VeriEQL wrapper (MISSING).
- 2026-10-03: checksum = MD5 of the result rows rendered as text, sorted, joined; plus the row count. Order-independent by construction (tested).
- 2026-10-03: what is verified now: building the recommended indexes on the twin leaves Q1's result unchanged (POST /v1/twin/checksum with {template_id, config}). The query replayed is Q1's logged query translated with the twin's frequency-rank map.
- 2026-10-03: status labels follow the doc: with VeriEQL MISSING, a matching checksum is "TestedOnly" (checksum passes, VeriEQL not run), a mismatch "Rejected". "Verified" needs VeriEQL.
- 2026-10-03: original-vs-rewritten SQL returns 501: rewrites are out of scope this session.
- 2026-10-03: VeriEQL wrapper BUILT (step 21), superseding the "MISSING" plug-in line above. POST /check on port 8300 runs each check in a child process killed at verify.verieql_timeout_s (60); bound verify.verieql_rows_per_table (5) rows per table, so "pass" is bounded model checking, not a proof for every size. Results: pass, fail (counterexample), unsupported (cannot encode, or timeout). Request logging is off so real SQL never lands in container logs.
- 2026-10-03: status rules for rewrites (gateway/service.py check_rewrite): Verified = VeriEQL pass and the twin checksums of original and rewritten match; TestedOnly = VeriEQL unsupported or not run and checksums match; Rejected = VeriEQL fail or a checksum mismatch. The index line on the twin panel stays TestedOnly by definition: VeriEQL checks rewrites, not indexes.
- 2026-10-03: measured capability: VeriEQL cannot encode date_trunc (NotImplementedError), so Q2's rewrite is TestedOnly (human decision: report it honestly). The two-region OR to IN rewrite is Verified. db/sandbox/verieql.py ASSUMPTION, stated in its docstring: numeric columns are modelled as INT.
