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
| Egress for ai | infra/egress_proxy.py, infra/docker-compose.yml | REAL CONNECT-only allowlist proxy, LLM host only; SIMPLIFIED: checks the host name, not traffic inside TLS | infra/tests/test_isolation.py, test_egress_proxy.py |
| QuickMart schema, generator, canaries, workload runner | db/ | REAL at 10,000,000 sales rows (human decision 2026-10-03: the free Gemini tier timed out at 50M); generator and twin stream in chunks; make seed 109 s, Q1 median 185 ms; slow_query_ms 100 (human-approved). Workload: Q1, Q2 and a two-region query added for the rewrite demo (step 21) | step 21 full tools suite on the 10M stack (db/tests included): 446 passed, 2 failed, 2 skipped; the 2 failures were Q1-only assumptions, fixed by a human-approved test change (miner/NOTES.md), both files then 7 passed |
| Gateway: hashing, stripping, ingestion, ledger, canary scan, resolver, API | gateway/ | REAL for the Q1 and Q2 flows, including /v1/rewrite/candidates and /v1/rewrite/verify (step 21); /v1/approve built in step 26 (see the Approve row); 2026-10-04: recorded twin mode estimates unrecorded configs from HypoPG costs (estimate_twin, human decision, not labelled), and 4 /v1/private/* endpoints (names, slow-log, slow-log/random, tables) for the local web app, refused to ai | gateway/tests/test_units.py, gateway/tests/test_api.py (17), gateway/tests/test_rewrite_rules.py (13), test_twin_estimate.py (3), test_private_endpoints.py (4) |
| FP-Growth miner | miner/, agent/api.py /ai/mine | REAL (covered-index check SIMPLIFIED: only primary keys are known as existing indexes; drift MISSING) | miner/tests/test_fpgrowth.py (8), miner/tests/test_q1_candidate.py (1) |
| Runtime predictor | models/gnn/predictor.py, agent/api.py /ai/gnn/predict | REAL: load_predictor() serves the trained GNN (models/gnn/weights) because results.json shows it beats the calibrated Postgres baseline; label "estimator: GNN, median q-error 1.59 on unseen templates". CostPredictor remains the fallback | models/gnn/tests (local venv, 2026-10-04); live Q1 test needs the stack, not run |
| Configuration search | rl/search.py, agent/api.py /ai/rl/run | REAL tabular Q-learning over index and rewrite actions; top 3 re-checked on the twin, best measured wins; result cache keyed on actions and the slow-template set; SIMPLIFIED: partition and drop-index actions MISSING | rl/tests (incl. test_rewrites.py, test_rl_run_api.py live), integration run 2026-10-03 |
| HypoPG what-if | db/sandbox/hypopg.py, gateway /v1/simulate/hypopg | REAL | db/sandbox/tests/test_hypopg.py |
| Twin measurement (before/after, storage, plan agreement, write cost) | db/sandbox/twin_measure.py, db/sandbox/write_cost.py, gateway/service.py estimate_twin | REAL on the twin in sandbox.twin_mode live; write cost = pgbench median insert latency with minus without indexes (WAL flush excluded); Q1 index +0.03 ms. In recorded mode (the default since 2026-10-04) an unrecorded config is answered by estimate_twin: measured mean_ms x the HypoPG plan cost ratio (floor estimate_min_ratio), a rewritten template capped at estimate_rewrite_ratio, index size = HypoPG x estimate_storage_scale (calibrated 280 MB to 68 MB on the Q1 index); human decision, not labelled on screen | db/sandbox/tests/test_write_cost.py, test_hypopg.py; gateway/tests/test_twin_estimate.py (3): Q1 index + Q2 rewrite estimate Q2 681 to 272 ms, Q1 188 to 62 ms, 69 MB |
| Statistical twin and fidelity | db/twin/build.py, db/sandbox/fidelity.py | SIMPLIFIED: from pg_stats, correlations kept for the column pairs the miner flags (region-7 share prod 30.01%, twin 30.00%); fidelity Q1 0.76, Q2 0.99, two-region 0.95 on a loaded machine | db/twin/tests, db/sandbox/tests/test_fidelity.py |
| LLM agent and number checker | agent/llm.py, agent/agent.py, agent/tools.py, agent/number_checker.py, /ai/ask | REAL; 8 of 8 doc tools; retries 429, 500/503/504 and failed connections. Providers: NVIDIA NIM is the default since 2026-10-04 (google/diffusiongemma-26b-a4b-it, human decision; answers Q1 in 7 to 51 s with 3 to 6 tool calls; the number checker blocked 2 of 4 live answers for invented figures, the rest of the page still renders), fallback gemini then openai (OpenAI model PENDING). Live failover seen 2026-10-04: NIM blocked at the egress proxy fell over to Gemini. Note: a container only picks up a new .env key or config.yaml when recreated (docker compose up -d), not on restart | agent/tests/test_agent.py (21); agent/tests/test_nim.py; agent/tests/test_llm_replay.py; agent/tests/test_failover.py (written, NOT RUN); agent/tests/test_live_llm.py (2, live gemini-3.8-flash); 4 live NIM Asks through site/web on 2026-10-04 |
| Checksum verification | verify/checksum.py, db/sandbox/checksum.py, gateway /v1/twin/checksum and /v1/rewrite/verify | REAL: an index leaves Q1's answer unchanged on the twin (TestedOnly by definition, VeriEQL checks rewrites only), and original vs rewritten results match on the twin (step 21) | verify/tests/test_checksum.py (4); gateway/tests/test_api.py rewrite tests (live) |
| Operator dashboard | dashboard/app.py (entry), dashboard/home.py (Ask page), dashboard/details.py (every other panel), dashboard/data.py, make demo | REAL; Ask page: question, LLM answer, time saved on the twin (estimate in recorded mode) with its assumption, SQL to apply and rollback SQL (from /v1/approve); falls back to its own search and twin measurement when the LLM fails; Details page keeps all earlier panels | dashboard/tests: 28 passed, 1 failed on 2026-10-04 (test_app.py::test_search_lists_rewrites_and_every_configuration_rechecked_on_the_twin expects "Final choice: best measured on the twin." but recorded search mode prefixes "recorded search result from <time>:"; assertion change needs human approval) |
| Q1 end-to-end test | e2e/test_q1.py, make e2e | REAL; passes at 10M rows with Q-learning | e2e/test_q1.py: 1 passed in 92.2 s (run_d1b30d38: twin 303.6 ms to 98.3 ms, 67.6% faster, measured while plan generation loaded the CPU; 43 payloads, 0 canary hits); tools suite 444 passed, 2 skipped |
| results.json export | scripts/export_results.py, make export, site/results.json | REAL; site/results.json is from run_9247c060 at commit f9ed1ccc2959 (2026-10-03T06:51:32Z) | scripts/tests/test_export_and_site.py; built pages scanned: no real names, canaries, dashes or numbers absent from results.json |
| Public site (5 pages, favicon) | site/, make site | REAL static site; MIT LICENSE added and terms point to it; results page renders run_9247c060; NOT DEPLOYED (needs the human's Vercel login); privacy and terms pending human review | scripts/tests/test_export_and_site.py (8 tests in the file) |
| Website (Next.js): home, playground, 8 stage pages, GNN, hashing, Ask with history, database sample, slow log, privacy, terms | site/web/, scripts/plans_web_sample.py, infra/docker-compose.yml `web` | REAL. Public build: illustrative codes only, no real names. Local web app (make up, 127.0.0.1:3000, or site/web/dev-local.sh on the host): the Ask button runs the live pipeline on NIM, every answer is saved as a bundle (src/lib/bundle.ts) in the web-history volume, the sidebar History reopens old questions, and the playground, stage pages, home, GNN (real logged plans, GNN predictions, gnn_explain, HypoPG plan) and hashing (real SQL vs gateway codes) pages render the selected question; /database shows real tables with sample rows, /slow-log the pg-prod templates plus 102 DSB, TPC-H and demo-copy templates from data/plans/web_sample.json with a random "Generate one". Hashing visualizer SIMPLIFIED (tokenizer, labelled). NOT DEPLOYED; privacy and terms pending human review | npm test 36 (logic, hashing, ask, bundle, spans, gnn, run-view); tsc and eslint clean; public build + scripts/tests -k web scan 7 passed (no real names, no /api/ask in chunks, every public route prerendered); scripts/tests/test_plans_web_sample.py (3); 4 live Asks on the host dev server and 1 through the web container on 2026-10-04 (bundle written to the volume after the Dockerfile chown fix); browser checks of every page with two bundles |
| Makefile | Makefile | REAL: keygen, up, down, seed, twin, demo, e2e, export, site and test targets. make up and make seed pass from a clean clone; make e2e fails there only because GEMINI_API_KEY is unset. infra/tests/run.sh assumes the default compose project name (blind-tuner) | every target dry-run with GNU Make 4.4.1 (make -n) in a container; GNU Make 4.3 is now installed on the dev machine and make test-all and make test-dashboard ran directly (step 21) |
| GNN features, export, model, scoring, serving | models/gnn/, db/plangen/export.py, agent/tools.py gnn_explain | REAL: weights trained on the 16,420-plan export, chosen on validation. On 3,133 test plans from 17 unseen templates: median q-error GNN 1.59, GBT 1.738, Postgres 3.266; p95 8.113, 12.144, 25.601; ranking 0.806, 0.761, 0.803; bottleneck 0.596 vs Postgres 0.585 (models/gnn/results.json) | models/gnn/tests, common/tests, contracts/tests, db/plangen/tests/test_export.py: passed in a local venv 2026-10-04; not yet rerun in the Docker image |
| DSB and TPC-H loading, plan generation | db/plangen/, infra/bench/, pg-bench | REAL: dsb SF1 (20.1M rows), tpch SF1 (8.66M), QuickMart copy (5.45M) loaded in 208 s; 200-plan sample committed (190 ran, 10 timed out, 0 errors); full run IN PROGRESS | make test-plangen: 20 passed (units, export, component against pg-bench) |
| Q2 and rule-based rewrites | db/workload.py, gateway/rewrite_rules.py, gateway/service.py, agent/tools.py, dashboard | REAL (step 21): 3 built-in sqlglot rules, label "rewrite rules: 3 built-in rules (R-Bot rule retrieval pending)"; Q2's rewrite TestedOnly (VeriEQL cannot encode date_trunc), the two-region OR to IN rewrite Verified. Q2 measured on the twin: rewrite alone 63.5% faster, rewrite + (store_id, transaction_date) 78.2%; the search chooses rewrites since step 23, but not the Q2 index (rl/NOTES.md); on the correlated twin Q2 measures 22% to 45% (gateway/NOTES.md) | gateway/tests/test_rewrite_rules.py (13); gateway/tests/test_api.py live rewrite tests; dashboard rewrite AppTest; e2e/test_q2.py (needs a live LLM; no passing run recorded) |
| Q4 and drift | gateway/windows.py, miner/drift.py, make drift-demo | REAL: JS distance per window, 2-window trigger; Q4 252.0 to 120.4 ms on the twin after the search re-ran. Q3 and partitioning MISSING | miner/tests/test_drift.py, test_drift_live.py |
| Adversarial leak test | privacy_tests/, agent/adversary.py | SIMPLIFIED: built and unit-tested; NO LIVE SCORE (Gemini free-tier daily quota exhausted) | privacy_tests/tests/test_adversarial.py |
| Air-gapped mode | agent/llm.py OllamaChat, infra/docker-compose.airgap.yml, make airgap/online/test-airgap | SIMPLIFIED: plumbing REAL and tested with a stand-in; real gemma2:2b UNVERIFIED (Ollama not installed yet) | agent/tests/test_ollama.py, infra/tests/test_airgap_network.py |
| VeriEQL | infra/verieql/, verify/verieql_server.py, db/sandbox/verieql.py, `verieql` service | REAL, bounded (5 rows per table, 60 s timeout, both in config). VeriEQL v1.0 is CC BY-NC-SA 4.0: isolated in its own image on the private network (human decision), must be replaced before commercial use. ASSUMPTION: numeric columns modelled as INT | VeriEQL's own test.test_env passes in the image; gateway/tests/test_api.py: Q2 TestedOnly, OR rewrite Verified, misfit rule 409 |
| Approve, migration and rollback | gateway/approve.py, gateway/post_deploy_check.py, /v1/approve, /v1/approve/twin-check | REAL; refuses the ai service (403); demo check on the twin with a shortened replay (labelled) | gateway/tests/test_approve.py |
