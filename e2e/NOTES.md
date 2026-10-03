# e2e/: notes

Owner: humans

Purpose: Scenario tests across the whole system.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: e2e/test_q1.py fails, never skips, when `GEMINI_API_KEY` is missing.

## Plug-in points not built yet

- Q2, drift, unparsable-query and invented-number scenarios (MISSING).
- 2026-10-03: e2e/test_q1.py is one test that drives the real services in order: slow templates, resolve (question carries the DBA canary), /ai/rl/run, /v1/simulate/twin, /v1/twin/checksum, /ai/ask, ledger. Asserts: Q1 mean above workload.slow_query_ms; first recommended index dehashes to `sales region_id transaction_date`; twin speedup above tests.q1_min_twin_speedup; checksum match; answer status ok with every cited tool_call_id among the run's tool calls; zero canary hits in this run's ai and llm ledger entries, and at least one llm entry; total time under tests.fast_suite_limit_s.
- 2026-10-03: the key check reads GEMINI_API_KEY_PRESENT, which compose sets to "yes" in the tools container only when .env has a key; the key itself never enters the tools container.
- 2026-10-03: a passing run writes runs/latest.json (gitignored): codes and measured numbers only, no real names.
- 2026-10-03: status: fails at the key check (no GEMINI_API_KEY yet). A diagnostic run with GEMINI_API_KEY_PRESENT=yes forced passed assertions 1 to 3 in 2.5 s and stopped at /ai/ask with 503 "GEMINI_API_KEY is not set". Assertions 4 and 5 have never run against a live LLM.
- 2026-10-03: e2e/test_q2.py (step 23): resolve "monthly category sales report" (canary in the question), /ai/rl/run, fresh /v1/simulate/twin, /v1/twin/checksum, /v1/rewrite/verify, /ai/ask, ledger. Asserts: Q2 slow; config holds Q2's date_trunc rewrite plus at least one index, final choice measured on the twin; Q2 twin speedup above tests.q2_min_twin_speedup; checksum match; rewrite TestedOnly in both verify and the search's check; the LLM called verify and its answer says TestedOnly; number checker ok; zero canary hits. No elapsed limit (the twin re-check takes minutes on a loaded machine); elapsed is printed. Writes no run record.
