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
