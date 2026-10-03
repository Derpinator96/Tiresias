# dashboard/: notes

Owner: Agent 4

Purpose: Streamlit operator dashboard. Shows real names, so it runs locally only and is never hosted publicly.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: bound to 127.0.0.1 on the `operator` network.

## Plug-in points not built yet

- Approve button (MISSING).
- Drift panel (MISSING).
- 2026-10-03: Streamlit 1.65.0 options, read from `streamlit config show` in the pinned image: `client.toolbarMode = "minimal"` hides the deploy button and developer options and, with nothing else set, the default menu; `browser.gatherUsageStats = false`; `browser.serverAddress = "127.0.0.1"` stops Streamlit fetching the public IP from checkip.amazonaws.com at startup (bootstrap.py only does that when serverAddress is unset and headless is true); theme `baseRadius`/`buttonRadius` 0.25rem (no pill buttons); primary colour #1F5F8B (no purple). The container runs from /app/dashboard because Streamlit reads .streamlit/config.toml from the working directory.
- 2026-10-03: panels: simplified-component labels; AI view / DBA view toggle (dehash through the gateway); ask box (resolved privately, answered by /ai/ask in a background thread, events polled every second, "rate limited" events shown as warnings); slow templates; Graphviz plan tree, child to parent, grey to red by predicted share; recommendation with predicted saving; twin before/after/speedup/storage with assumptions inline; checksum status; ledger counter; negative control; ledger export.
- 2026-10-03: the ledger counter includes the dashboard's own reads of AI-facing endpoints (they are ledgered as destination ai). Over-counting is the safe direction; the caption says so on screen.
- 2026-10-03: background ask jobs live in an st.cache_resource dict: a module-level dict was reset on every rerun, which left the panel stuck on "Agent working".
- 2026-10-03: the "rate limited, retrying" warning on screen is not covered by an automated test; agent/tests/test_agent.py proves the events are emitted.
- 2026-10-03: the plan tree is selectable per slow template (a selectbox of rank numbers plus the template, defaulting to rank 1, the slowest, as before). Rank numbers keep two options distinct when their cut-off query texts match.
- 2026-10-03: Approve panel at the end of app.py (supersedes "Approve button (MISSING)" above). It sends the search's Config plus every rewrite checked in the Rewrites panel and not Rejected (capped at the contract's 5 actions, with a warning if any are left out) to `/v1/approve`, and shows migration.sql, rollback.sql and post_deploy_check.py in expanders with download buttons. In the AI view it shows none of them, only a note. "Run the post-deploy check on the twin" calls `/v1/approve/twin-check` and shows each replayed template's median before and after, kept or rolled back, and the label `approve_demo` (twin, shortened replay).
