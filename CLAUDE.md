# Blind Tuner: rules for every agent
Read docs/architecture.md before any work. It is the single source of truth. If code and doc disagree, ask a human.

## Design
- No purple gradients. No pill-shaped buttons.
- No emoji used as icons. Use a real icon set or plain text labels.
- No scroll-triggered animation, parallax, custom cursors or cursor effects.
- No AI-generated photography or illustration.

## Copy
- No em dashes anywhere: UI copy, code comments, docs, commit messages.
- No vague hero text. Every heading states a fact or names a function.
- No AI filler copy. If a sentence could appear on any product, delete it.

## Honesty on screen
- No fabricated reviews, testimonials, logos or endorsements.
- No fake metrics, counters or customer numbers.
- Every number rendered traces to a real computation. If a figure rests on an assumption, label the assumption next to it, not in a footnote.
- Placeholder data is visibly labelled as placeholder.
- A simplified component is labelled on screen, for example "estimator: Postgres baseline (GNN pending)".

## Ship gates: nothing is done until all five are true
1. Clean memorable URL (a Vercel subdomain is fine, a raw AWS hostname is not).
2. Favicon present.
3. No builder or "Made with AI" badge anywhere.
4. Privacy policy page exists.
5. Terms and conditions page exists.

## Engineering
- Do not guess an API signature. Check the docs or the installed package version.
- If a claim is unverified, say so in the code comment and in your report.
- Tests before "done". If something cannot be tested, say so explicitly.
- Report what you did not finish. Silence is not completion.
- Never weaken a test to make it pass. Changing an assertion or threshold needs human approval.
- Never edit contracts/ or another owner's folder without human approval.
- After three failed attempts at one problem, stop and ask a human.
- Every tunable value lives in config.yaml, never in code.
- The HMAC key lives only in an uncommitted .env file. Never print, log or commit it.
- The operator dashboard is never hosted publicly. Only the static site in site/ is public.
- Record decisions in the relevant folder's NOTES.md.

## Current state
Update this table at the end of every work session. Status is REAL, SIMPLIFIED (say how), PLACEHOLDER or MISSING. "Tested" names the test that proves it, or says "untested" and why.

| What | Where | Status | Tested |
| --- | --- | --- | --- |
| Repo layout and NOTES.md per folder | all folders | REAL | clean clone of main on 2026-10-03: keygen, up and seed pass; all tools suites 350 passed, 2 skipped (live LLM); dashboard 5 passed |
| Interface contracts (JSON Schemas), 11 from the doc plus OutboundPayload | contracts/ | REAL | contracts/tests/test_contracts.py (119 passed) |
| config.yaml and loader | config.yaml, common/ | REAL | common/tests/test_config.py (governed-module check covers db/ and gateway/) |
| Docker Compose services and networks | infra/ | REAL (gateway uses the postgres superuser; SIMPLIFIED until least-privilege roles exist) | infra/tests/run.sh: test_isolation.py (6), test_private_no_internet.py (2), test_postgres.py (8) |
| Egress for ai | infra/ | SIMPLIFIED: unrestricted internet, no allowlist of the LLM API host | test_isolation.py::test_llm_api_host_is_reachable proves the route exists, not that other hosts are blocked |
| QuickMart schema, generator, canaries, workload runner | db/ | REAL at 10,000,000 sales rows (human decision 2026-10-03: the free Gemini tier timed out at 50M); generator and twin stream in chunks; make seed 109 s, Q1 median 185 ms; slow_query_ms 100 (human-approved). Workload: Q1, Q2 and a two-region query added for the rewrite demo (step 21) | step 21 full tools suite on the 10M stack (db/tests included): 446 passed, 2 failed, 2 skipped; the 2 failures were Q1-only assumptions, fixed by a human-approved test change (miner/NOTES.md), both files then 7 passed |
| Gateway: hashing, stripping, ingestion, ledger, canary scan, resolver, API | gateway/ | REAL for the Q1 and Q2 flows, including /v1/rewrite/candidates and /v1/rewrite/verify (step 21); /v1/approve returns 501 (step 26 on its own branch) | gateway/tests/test_units.py, gateway/tests/test_api.py (17), gateway/tests/test_rewrite_rules.py (13) |
| FP-Growth miner | miner/, agent/api.py /ai/mine | REAL (covered-index check SIMPLIFIED: only primary keys are known as existing indexes; drift MISSING) | miner/tests/test_fpgrowth.py (8), miner/tests/test_q1_candidate.py (1) |
| Runtime predictor | models/gnn/predictor.py, agent/api.py /ai/gnn/predict | SIMPLIFIED: Postgres cost x a ratio measured from the baseline plan; label "estimator: Postgres cost x calibration (GNN pending)" | models/gnn/tests/test_predictor.py (4) |
| Configuration search | rl/search.py, agent/api.py /ai/rl/run | REAL tabular Q-learning (optimistic init, best visited config) with greedy reported alongside; SIMPLIFIED: index actions only, top-3 twin re-check pending; label "search: Q-learning, index actions only (rewrite, partition and top-3 twin re-check pending)". lambda_storage 0.25 (human-approved) | rl/tests/test_search.py, rl/tests/test_qlearning.py (beats greedy on overlapping indexes; adapts to new weights without restarting); live: same pick as greedy on Q1 |
| HypoPG what-if | db/sandbox/hypopg.py, gateway /v1/simulate/hypopg | REAL | db/sandbox/tests/test_hypopg.py |
| Twin measurement (before/after, storage, plan agreement) | db/sandbox/twin_measure.py, gateway /v1/simulate/twin | REAL measurement on the SIMPLIFIED twin; write cost not measured (write_ms_delta null, pgbench MISSING) | db/sandbox/tests/test_hypopg.py::test_gateway_twin_endpoint_measures_q1_speedup, db/twin/tests/test_twin.py::test_q1_plan_agrees_and_index_speeds_it_up |
| Statistical twin | db/twin/build.py, make twin | SIMPLIFIED: columns generated independently from pg_stats, no correlations; label "twin: synthetic from pg_stats, no column correlations yet". sales at full size (10,000,000), others 20% or the FK distinct floor | db/twin/tests/test_twin.py (8) |
| LLM agent and number checker | agent/llm.py, agent/agent.py, agent/tools.py, agent/number_checker.py, /ai/ask | REAL; 8 of 8 doc tools (rewrite_candidates and verify added in step 21; prompt rule 4: rewrites only through those tools); retries 429 and 500/503/504 | agent/tests/test_agent.py (21, scripted model and mock transport); agent/tests/test_live_llm.py (2, live gemini-3.8-flash) |
| Checksum verification | verify/checksum.py, db/sandbox/checksum.py, gateway /v1/twin/checksum and /v1/rewrite/verify | REAL: an index leaves Q1's answer unchanged on the twin (TestedOnly by definition, VeriEQL checks rewrites only), and original vs rewritten results match on the twin (step 21) | verify/tests/test_checksum.py (4); gateway/tests/test_api.py rewrite tests (live) |
| Operator dashboard | dashboard/app.py, dashboard/data.py, make demo | REAL; every simplified component labelled on screen; ledger counter includes the dashboard's own reads (labelled); Rewrites panel at the page end (step 21) | dashboard/tests/test_app.py (6, AppTest); "rate limited" warning display untested |
| Q1 end-to-end test | e2e/test_q1.py, make e2e | REAL; passes at 10M rows with Q-learning | e2e/test_q1.py: 1 passed in 92.2 s (run_d1b30d38: twin 303.6 ms to 98.3 ms, 67.6% faster, measured while plan generation loaded the CPU; 43 payloads, 0 canary hits); tools suite 444 passed, 2 skipped |
| results.json export | scripts/export_results.py, make export, site/results.json | REAL; site/results.json is from run_9247c060 at commit f9ed1ccc2959 (2026-10-03T06:51:32Z) | scripts/tests/test_export_and_site.py; built pages scanned: no real names, canaries, dashes or numbers absent from results.json |
| Public site (5 pages, favicon) | site/, make site | REAL static site; MIT LICENSE added and terms point to it; results page renders run_9247c060; NOT DEPLOYED (needs the human's Vercel login); privacy and terms pending human review | scripts/tests/test_export_and_site.py (8 tests in the file) |
| Makefile | Makefile | REAL: keygen, up, down, seed, twin, demo, e2e, export, site and test targets. make up and make seed pass from a clean clone; make e2e fails there only because GEMINI_API_KEY is unset. infra/tests/run.sh assumes the default compose project name (blind-tuner) | every target dry-run with GNU Make 4.4.1 (make -n) in a container; GNU Make 4.3 is now installed on the dev machine and make test-all and make test-dashboard ran directly (step 21) |
| GNN features, export, model, scoring, serving | models/gnn/, db/plangen/export.py, agent/tools.py gnn_explain | REAL pipeline; TRAINING by a separate trainer (not delivered). Reference loop on the 200-plan sample only: GNN median q-error 2.47 vs Postgres 2.54 vs scikit-learn GBT 1.56 on 40 test plans (too small to conclude). Serving falls back to the Postgres baseline until scored weights beat it | models/gnn/tests (test_gnn, test_serving), db/plangen/tests/test_export.py, agent/tests gnn_explain; step 19 tools suite 439 passed, 2 skipped |
| DSB and TPC-H loading, plan generation | db/plangen/, infra/bench/, pg-bench | REAL: dsb SF1 (20.1M rows), tpch SF1 (8.66M), QuickMart copy (5.45M) loaded in 208 s; 200-plan sample committed (190 ran, 10 timed out, 0 errors); full run IN PROGRESS | make test-plangen: 20 passed (units, export, component against pg-bench) |
| Q2 and rule-based rewrites | db/workload.py, gateway/rewrite_rules.py, gateway/service.py, agent/tools.py, dashboard | REAL (step 21): 3 built-in sqlglot rules, label "rewrite rules: 3 built-in rules (R-Bot rule retrieval pending)"; Q2's rewrite TestedOnly (VeriEQL cannot encode date_trunc), the two-region OR to IN rewrite Verified. Q2 measured on the twin: rewrite alone 63.5% faster, rewrite + (store_id, transaction_date) 78.2%; the search does not yet choose rewrites (step 23 on its own branch) | gateway/tests/test_rewrite_rules.py (13); gateway/tests/test_api.py live rewrite tests; dashboard rewrite AppTest; e2e/test_q2.py pending step 23 |
| Q3, Q4, partitioning, drift | db/, miner/, rl/ | MISSING on this branch (drift and Q4: step 25 branch; partitioning after step 23 merges) | untested |
| Adversarial leak test | privacy_tests/ | MISSING (out of scope this session) | untested |
| Air-gapped mode | infra/, agent/ | MISSING (out of scope this session) | untested |
| VeriEQL | infra/verieql/, verify/verieql_server.py, db/sandbox/verieql.py, `verieql` service | REAL, bounded (5 rows per table, 60 s timeout, both in config). VeriEQL v1.0 is CC BY-NC-SA 4.0: isolated in its own image on the private network (human decision), must be replaced before commercial use. ASSUMPTION: numeric columns modelled as INT | VeriEQL's own test.test_env passes in the image; gateway/tests/test_api.py: Q2 TestedOnly, OR rewrite Verified, misfit rule 409 |
| Approve, migration and rollback scripts | gateway/, dashboard/ | MISSING (out of scope this session) | untested |
| Twin correlations | db/twin/ | MISSING (out of scope this session) | untested |
