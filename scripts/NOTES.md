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
