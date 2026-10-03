# scripts/: notes

Owner: humans (not assigned in the doc)

Purpose: Utility scripts, starting with the results.json exporter.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: results.json is exported from the latest real e2e run and includes the run ID, timestamp, dataset size, git commit hash, and each number's assumption.
- 2026-10-03: `scripts/export_results.py` refuses to write site/results.json unless runs/latest.json exists (written only by a passing make e2e). The git commit is read from .git directly because the Python image has no git binary. Each exported number carries source and assumption.
- 2026-10-03: as of this commit no e2e run has passed (no GEMINI_API_KEY), so site/results.json does not exist and the results page shows a labelled placeholder.
- 2026-10-04: scripts/public_names.py holds the forbidden public names (moved from the site test, unchanged) and leaks(); the site tests and record_ask.py share it.
- 2026-10-04: scripts/record_ask.py (`make record-ask`) records one live Ask session for the public /ask page: question id, template codes, hashed answer and numbers, checker status, events, config, simulation, ledger totals. Never the question text, dehashed text or approve files. Refuses to write on a forbidden name, a canary value or a dash. Not run yet (needs the stack and an LLM key).
- 2026-10-04: scripts/plans_web_sample.py (bench container: `docker compose ... --profile bench run --rm -T bench python -m scripts.plans_web_sample`) writes data/plans/web_sample.json: one entry per (database, template_id) of db.plangen.run.workload() with the parameter-set-0 SQL and statistics streamed once from data/plans/plans.jsonl (kept plans, median and max runtime, timeouts, node count of one kept plan, top 3 node types over every kept plan of the template). Without the DSB and TPC-H kits it writes the QuickMart templates only and says so in "note". The file holds real names and benchmark SQL: it stays under data/ (un-ignored) and is read only by the local web app (BT_PLANS_SAMPLE). First run: 102 templates, 16,420 plans. Unit test: scripts/tests/test_plans_web_sample.py (3, in-memory plans, no Docker).
