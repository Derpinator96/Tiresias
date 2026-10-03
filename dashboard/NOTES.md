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
- 2026-10-03 (step 27): "Adversarial leak test" panel at the end of app.py. Reads runs/adversarial.json through a read-only mount of ./runs (data.adversarial()); shows the adversary's hit count and rate, the random common-name baseline, the plaintext upper bound (labelled as by construction), what share of the run it saw, and LABELS["adversarial"] (equal to privacy_tests/adversarial.py LABEL). With no file it says how to produce one. LABELS["egress"] now names the allowlist proxy (equal to infra/egress_proxy.py LABEL).
