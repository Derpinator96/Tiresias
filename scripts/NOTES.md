# scripts/: notes

Owner: humans (not assigned in the doc)

Purpose: Utility scripts, starting with the results.json exporter.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: results.json is exported from the latest real e2e run and includes the run ID, timestamp, dataset size, git commit hash, and each number's assumption.
- 2026-10-03: `scripts/export_results.py` refuses to write site/results.json unless runs/latest.json exists (written only by a passing make e2e). The git commit is read from .git directly because the Python image has no git binary. Each exported number carries source and assumption.
- 2026-10-03: as of this commit no e2e run has passed (no GEMINI_API_KEY), so site/results.json does not exist and the results page shows a labelled placeholder.
