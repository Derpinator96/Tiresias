# site/: notes

Owner: humans (not assigned in the doc)

Purpose: Public static site deployed to Vercel. No database access, no real names, no raw values.

Record every decision here with its date, so a fresh session can pick up without losing context.

## Decisions

- 2026-10-03: Vercel project `blind-tuner`; if taken, `blind-tuner-demo`.
- 2026-10-03: the privacy policy and terms describe only what is true of this site and need human review before deploy.
- 2026-10-03: built by `site/build.py` (Python, run in the tools container), not a JS toolchain: pages are HTML fragments in site/src wrapped in one layout; the results page is rendered from site/results.json only, values exactly as exported (no re-rounding). No scripts, no fonts or assets from other hosts, no forms, no cookies.
- 2026-10-03: there is no site/__init__.py on purpose: a package named `site` on PYTHONPATH would shadow the standard library module Python imports at startup. Tests load build.py by path.
- 2026-10-03: the site never shows QuickMart's table or column names; scripts/tests/test_export_and_site.py checks every built page against the list, plus canaries, em dashes, builder badges and scripts. The example code on the home page (t_7a3f91c2) is illustrative, not a real-key code.
- 2026-10-03: build empties site/dist but keeps site/dist/.vercel (the project link). Deploy commands (checked against https://vercel.com/docs/cli/link): `cd site/dist && vercel link --yes --project blind-tuner && vercel deploy --prod`.
- 2026-10-03: the privacy policy and terms state only what is true of this site (static, no collection, Vercel request logs). They need human review before deploy. The repository has no LICENSE file, so the terms grant no rights to the code; add a license if that is wrong.
- 2026-10-03: a human chose the MIT License for the repository (LICENSE at the root, holder "the Blind Tuner contributors"). The terms page now points to it. Privacy and terms still need human review before deploy.
- 2026-10-03: site/web is a Vite + React presentation site for the jury (grayscale, no build-time data fetch). Every figure is hardcoded in site/web/src/data.js from measured runs, with the source of each named in its header comment. Deploy on Vercel with root directory site/web (vercel.json: framework vite, output dist). The GNN figure is the reference model's result; replace it when the trainer's weights are scored.
- 2026-10-03: site/web (the React jury site) deleted on a human's decision; the frontend will be rebuilt later. It had no privacy or terms page and loaded Google Fonts, against site/src/privacy.html. The static site/ (privacy, terms, favicon) is the deploy target until then. site/results.json is not refreshed: export stamps the current commit, and runs/latest.json (run_d1b30d38) does not record the commit it ran on, so a re-export now would misattribute it; a fresh live e2e run is needed (no live LLM calls this session, human decision).
- 2026-10-04: site/web recreated by a human's request as a basic Next.js, Tailwind and shadcn scaffold (see site/web/NOTES.md). Not part of make site and not public. docs/frontend-context.md holds the project context for front-end work.
- 2026-10-04: a human decided the Next.js app in site/web replaces this static site as the public deploy (Vercel root directory site/web). site/build.py, site/src and their tests stay until the switch is confirmed; site/results.json (run_9247c060) is not used by the new site, which reads run_d1b30d38.
