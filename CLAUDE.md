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
