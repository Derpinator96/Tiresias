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
| Repo layout and NOTES.md per folder | all folders | REAL | untested: no code yet; `ls` output in PR for step 1 |
| Interface contracts (JSON Schemas), 11 from the doc plus OutboundPayload | contracts/ | REAL | contracts/tests/test_contracts.py (119 passed) |
| config.yaml and loader | config.yaml, common/ | REAL (slow_query_ms is a PROPOSED 10 ms pending approval; llm.model not yet confirmed against the API) | common/tests/test_config.py (governed-module check covers db/ and gateway/) |
| Docker Compose services and networks | infra/ | REAL (gateway uses the postgres superuser; SIMPLIFIED until least-privilege roles exist) | infra/tests/run.sh: test_isolation.py (6), test_private_no_internet.py (2), test_postgres.py (8) |
| Egress for ai | infra/ | SIMPLIFIED: unrestricted internet, no allowlist of the LLM API host | test_isolation.py::test_llm_api_host_is_reachable proves the route exists, not that other hosts are blocked |
| QuickMart schema, generator, canaries, Q1 runner | db/ | REAL at 1,000,000 sales rows (not the doc's 50M; Q1 median 24.9 ms, so slow_query_ms is a PROPOSED 10 ms pending approval) | db/tests/test_quickmart.py (33 passed) |
| Gateway: hashing, stripping, ingestion, ledger, canary scan, resolver, API | gateway/ | REAL for the Q1 flow (simulate and checksum endpoints return 501 until steps 9, 10, 12; approve out of scope) | gateway/tests/test_units.py, gateway/tests/test_api.py (47 passed) |
| FP-Growth miner | miner/, agent/api.py /ai/mine | REAL (covered-index check SIMPLIFIED: only primary keys are known as existing indexes; drift MISSING) | miner/tests/test_fpgrowth.py (8), miner/tests/test_q1_candidate.py (1) |
| Runtime predictor | models/gnn/predictor.py, agent/api.py /ai/gnn/predict | SIMPLIFIED: Postgres cost x a ratio measured from the baseline plan; label "estimator: Postgres cost x calibration (GNN pending)" | models/gnn/tests/test_predictor.py (4) |
| Configuration search | rl/ | MISSING (planned SIMPLIFIED: greedy, RL pending) | untested: step 9 |
| HypoPG what-if | db/sandbox/ | MISSING | untested: step 10 |
| Statistical twin | db/twin/ | MISSING (planned SIMPLIFIED: no correlations) | untested: step 10 |
| LLM agent and number checker | agent/ | MISSING | untested: step 11 |
| Checksum verification | verify/ | MISSING | untested: step 12 |
| Operator dashboard | dashboard/ | MISSING | untested: step 13 |
| Q1 end-to-end test | e2e/ | MISSING | untested: step 14 |
| results.json export and public site | scripts/, site/ | MISSING | untested: step 15 |
| Makefile | Makefile | MISSING | untested: step 16 |
| GNN training, XGBoost baseline | models/gnn/ | MISSING (out of scope this session) | untested |
| Q-learning | rl/ | MISSING (out of scope this session) | untested |
| DSB and TPC-H loading, plan generation | db/ | MISSING (out of scope this session) | untested |
| Q2 to Q4, partitioning, drift | db/, miner/, rl/ | MISSING (out of scope this session) | untested |
| Adversarial leak test | privacy_tests/ | MISSING (out of scope this session) | untested |
| Air-gapped mode | infra/, agent/ | MISSING (out of scope this session) | untested |
| VeriEQL | verify/ | MISSING (out of scope this session) | untested |
| Approve, migration and rollback scripts | gateway/, dashboard/ | MISSING (out of scope this session) | untested |
| Twin correlations | db/twin/ | MISSING (out of scope this session) | untested |
| ai and dashboard apps | agent/api.py, dashboard/app.py | PLACEHOLDER: /healthz only and a dashboard page saying so | test_isolation.py::test_gateway_is_reachable |
