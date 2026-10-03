# privacy_tests/: notes

Owner: Agent 2

Purpose: Adversarial leak test and negative-control suite.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- None yet.

## Plug-in points not built yet

- Adversarial leak test: built 2026-10-03 (step 27), see the decisions below. No live score yet.
- Negative-control suite (MISSING; the dashboard button calls the gateway endpoint directly).

## Step 27: adversarial leak test (2026-10-03)

- Doc: Component 7, Proof 3 step 3, and Detailed component specs, Privacy tests: "give a fresh LLM session the full ledger of one run and ask it to name the real table and column behind each code. A script scores exact and synonym matches and compares with random guesses from a list of common names."
- Flow. The gateway now keeps the bytes of every allowed payload to ai or the LLM (gateway/NOTES.md). `make adversarial` (privacy_tests/adversarial.py, tools container) posts a time window to ai's `POST /ai/privacy/adversary`; ai fetches that window's payloads from the gateway (`GET /v1/ledger/payloads`, itself scanned and ledgered), builds one prompt (agent/adversary.py) and sends it through llm.generate with no tools, so the adversarial request is canary-scanned and ledgered like every other LLM payload. ai returns the guess per code; the tools side resolves the real names through the gateway's dehash endpoint and scores.
- Split: nothing on the ai side knows a real name. The synonym and common-name lists hold real QuickMart names, so they live here, never mounted into ai.
- Window: `make adversarial` defaults to the last passing e2e run (runs/latest.json: finished_at minus elapsed_s, with a second of slack); `SINCE=` and `UNTIL=` take any window. An earlier adversary request inside the window is left out (it is a re-send).
- Material budget: `privacy.adversarial_max_chars` (120,000). One live Q1 ask produced 223 distinct payloads, 769,666 characters, most of them ~200 HypoPG costings from the Q-learning search. LLM request bodies go first (what the provider saw), then AI-side payloads in time order, skipping what overflows. At 100,000 characters all 4 LLM bodies and all 37 table and column codes are already in. The result reports payloads and characters sent out of the window's total.
- Scoring: exact (after lowercasing, stripping quotes and a `table.` prefix, spaces to underscores) or synonym (small fixed list per real name, `SYNONYMS`); a skipped code scores none. Baseline: expected hit rate of one uniform random guess per code from 40 common table names or 60 common column names (`COMMON`), computed exactly, not sampled. The lists were written as generic schema vocabulary; they include QuickMart's own names where those are common, which is what chance level means.
- Values: the doc's Proof 3 also says "and any values". Not asked or scored: literals never leave as values (they are `?`), and the canary scan covers them. Labelled on screen.
- Plaintext control: the doc asks to compare with a plaintext control. Real names are never sent to the external LLM, not even as a control. The file reports the plaintext upper bound by construction (plaintext payloads carry every name verbatim: 100%), labelled as an assumption; an LLM run on plaintext is pending air-gapped mode (local model).
- Output: runs/adversarial.json (gitignored like runs/latest.json). Keys: finished_at, window {since, until}, llm {provider, model, temperature, llm_payload_id, guesses_returned}, material {payloads_in_window, payloads_sent, chars_in_window, chars_sent, llm_payloads_sent}, codes_unresolved, hashed {all, table, column: {codes, exact, synonym, exact_rate, rate}}, baseline_random_common_names {exact_rate, rate, table_names_listed, column_names_listed}, plaintext_upper_bound {rate, assumption}, plaintext_llm_control, per_code [{code, kind, match}], label. No real name and no guess is written, so it can be exported as is. The dashboard reads it through a read-only mount of runs/.
- Live run, 2026-10-03, NOT COMPLETED. The window was one live Q1 ask (make test-llm, 2026-10-03T10:33:30.403585+00:00 to 2026-10-03T10:37:06.080615+00:00 on the bt-privacy stack: 228 ledger entries, 4 LLM bodies, 0 canary hits). Three adversary attempts reached the LLM API through the egress proxy, each canary-scanned and ledgered (verdict allow, 0 hits), and each got HTTP 429 on all 5 retries: the first two at 300,000 and 120,000 characters, the third named the quota GenerateRequestsPerDayPerProjectPerModel-FreeTier (the shared free key's daily limit for gemini-3.8-flash). No score exists yet. To finish once the quota resets: `make adversarial SINCE=2026-10-03T10:33:30.403585+00:00 UNTIL=2026-10-03T10:37:06.080615+00:00` on the bt-privacy stack (its gateway volume holds that window's bodies), or `make e2e && make adversarial` on any stack.
- Tests: privacy_tests/tests/test_adversarial.py (scorer on toy guesses, baseline, parser, budget, one tool-free request, no LLM call without codes, an earlier adversary request left out, label equals the dashboard's). No component test drives a live adversary run: it needs the LLM (budget) and the quota.
