# Blind Tuner: what is left (2026-10-04, main e2f3709)

Status words: DONE, PARTIAL, MISSING. Each item cites the file or NOTES.md line it comes from.

## 1. Do we need to train the RL?

No. `rl/search.py` is tabular Q-learning that learns online inside every `/ai/rl/run`. There are no weights to train or ship. The Q-table lives in memory in the `ai` process and survives across runs (drift keeps learning), but a restart empties it. The GNN is what changes the RL: when its weights serve, the reward model swaps, so re-validate the RL then (do not retrain).

## 2. PS4 mapped to the code

| PS4 asks for | Status | Evidence or gap |
| --- | --- | --- |
| Bitmasking and metadata hashing | DONE | gateway/, canary scan, ledger, AI-view toggle |
| Ingest anonymised logs and plans | DONE | gateway/ingest; unparsable SQL withheld and logged (step 34, `GET /v1/withheld`) |
| Composite indexes via RL | DONE | Q1 (region_id, transaction_date) |
| Partitioning via RL | DONE (step 32) | monthly range partition scored on the twin only, at most `rl.partition_max_keys` keys; Q3 217.8 to 46.2 ms on the twin, fidelity 0.975 |
| Sharding | DONE as written advice | migration.sql block labelled "written advice only" |
| Rewrite SQL | DONE | 3 sqlglot rules, VeriEQL plus twin checksum; R-Bot RAG MISSING |
| GNN explanations | PARTIAL | reason, evidence and twin line on every recommended action (step 33); serving still the Postgres cost fallback until trainer weights land |
| Write latency and storage simulation | DONE | pgbench and measured MB on the twin |
| Interactive dashboard | DONE | Ask page (home.py) and Details page (details.py) |
| Zero exposure, proven | PARTIAL | canaries and negative control done; adversarial test has no live score |
| Over 50% on joins (Q2) | AT RISK | correlated twin measures Q2 at 22% to 45% (`gateway/NOTES.md`); search never picks the Q2 index (`rl/NOTES.md`) |
| RL robust to evolving patterns | DONE | drift live test and offline e2e drift scenario; RL vs greedy shown in the drift panel |

## 3. P0: before the demo

### Verify what was pushed (tests were skipped at push time)
- [ ] `make test-all` on main (stopped at 60% before the push, no failures until then).
- [ ] `make test-dashboard` (Ask page from PR #22 has never run against partition actions).
- [ ] `make e2e-offline` on main.
- [ ] One live `make e2e` (Q1 and Q2) with Gemini.

### Known risks from step 32 (human decisions)
- [ ] Partition step adds about 80 s per key; a cold `/ai/rl/run` is about 190 to 230 s, near the dashboard's 300 s HTTP timeout. `e2e/test_q1` has a 120 s limit and will likely fail. Options: raise the limit, or `rl.partition_max_keys: 0` for that run.
- [ ] `workload.q3_in_seed` is false. With Q3 seeded, the Q1 index stops paying (HypoPG sizes it at 280 MB, `lambda_storage` 0.25) and the Q1 test fails. If turned on, add q3 to `workload.drift_before`.
- [ ] `/v1/twin/checksum` checks only indexes, not the partitioned copy.

### GNN handoff (separate owner)
- [ ] Drop `gnn.pt` and `meta.json` into `models/gnn/weights/`, run `python -m models.gnn.evaluate`, confirm `/ai/gnn/estimator` says gnn, re-run e2e.

### Q2 target
- [ ] Find a Q2 fix that clears 50% on the correlated twin, or state the miss on screen. Measure and propose only; config and threshold changes need a human.

### Ship gates
- [ ] Deploy the static `site/` to Vercel (human login). The React site was deleted; a new frontend comes later.
- [ ] Human review of privacy and terms.
- [ ] Refresh `site/results.json` from a fresh passing live e2e (the current one is run_9247c060, 1M rows).

## 4. P1

- [ ] Least-privilege Postgres roles for the gateway (uses the superuser today, `infra/NOTES.md`).
- [ ] Drop-index action; covered-index check beyond primary keys.
- [ ] Carry `loops` in HashedPlan (contract change, human approval) so gnn_explain can compare Nested Loop inner nodes instead of skipping them.
- [ ] Remove the stale `bt-airgap_llm-local` Docker network if nobody uses it (it blocks a second stack from running the invented-number scenario).
- [ ] `scripts/tests/test_export_and_site.py::test_git_commit_is_a_full_hash` fails inside git worktrees (`.git` is a file there).

## 5. Fine-tuning (config.yaml, each change needs human approval)

| Knob | Today | Why |
| --- | --- | --- |
| `rl.lambda_write`, `rl.write_penalty_ms_per_index` | 1.0, 0.1 ms | units mix ms with a unitless drop; measured 0.032 ms per insert |
| `rl.lambda_storage` | 0.25 | HypoPG overestimates btree size (280 vs 76 MB), blocks the Q2 index and the Q1 index once Q3 is seeded |
| `rl.lambda_disagreement` | 1.0 | inactive until the GNN serves |
| `rl.episodes`, `rl.partition_max_keys` | 300, 2 | cold search time vs the 120 s e2e limit |

## 6. P2 and out of scope this session

- Ablations, Supabase index_advisor baseline, hashed vs plaintext answer quality, R-Bot rules, real Ollama verification: skipped by human decision (no installs, no live calls).
- Optional: persist the Q-table to disk.
- Demo: three clean runs in a row, backup video, cached hero run.
