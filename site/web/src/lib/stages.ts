// The 8 pipeline stages and the copy of their deep-dive pages. Plain module (no "use client"), so
// server pages can read it. Every figure carries its source and, where it rests on one, its
// assumption. Copy is written from docs/architecture.md (components 1 to 8) and the NOTES.md files,
// with the demo database's real names left out (public pages never show them).
import { CANARIES, CODES_LABEL, CONFIG, INDEX_COLS, WRITE_COST, run } from "@/lib/facts";

export const STAGES = [
  { id: "source", title: "Postgres Source" },
  { id: "gateway", title: "Privacy Gateway" },
  { id: "miner", title: "Pattern Miner" },
  { id: "gnn", title: "GNN Estimator" },
  { id: "rl", title: "RL Search" },
  { id: "llm", title: "LLM Agent" },
  { id: "twin", title: "Twin Sandbox" },
  { id: "dba", title: "DBA Console" },
] as const;
export type StageId = (typeof STAGES)[number]["id"];

export const STAGE_SUMMARY: Record<StageId, string> = {
  source: "Postgres logs the slow query shape; values are already $1.",
  gateway: "Hashes names, strips values, scans every payload for canaries.",
  miner: "FP-Growth over hashed queries proposes composite indexes.",
  gnn: "Estimates runtimes of plans that have never run; the Postgres baseline serves until the GNN is scored.",
  rl: "Q-learning picks the best set of fixes under a write and storage budget.",
  llm: "Explains the fix in plain words; every number is checked.",
  twin: "Measures the fix on a synthetic copy, never on production.",
  dba: "Signed-off migration and rollback; the DBA runs them by hand.",
};

export type Figure = { label: string; value: string; source: string };
export type Status = { state: "REAL" | "SIMPLIFIED" | "PLACEHOLDER" | "MISSING"; text: string };
export type StageCopy = {
  heading: string; // states a fact
  lead: string;
  steps: string[];
  sent?: string[];
  never?: string[];
  figures: Figure[];
  status: Status[];
  failures: [string, string][];
  sources: string;
};

const ms = (x: number) => `${x.toFixed(1)} ms`;
const distinctCanaries = new Set(CANARIES.map((c) => c[0])).size;

export const STAGE_COPY: Record<StageId, StageCopy> = {
  source: {
    heading: "Postgres already logs the slow query without its values",
    lead: "Nothing new runs inside the production database. Blind Tuner reads what Postgres records anyway: query shapes from pg_stat_statements and executed plans from auto_explain.",
    steps: [
      "pg_stat_statements groups every query by shape and keeps calls and total time. Values in the logged text are already $1, $2.",
      "auto_explain logs the executed plan of any query slower than the threshold, with estimated and actual rows per node.",
      "The hero query, Q1, sums one column of the hero table for one value of an equality column and a date range. Without an index Postgres reads every row to keep a small fraction.",
      "One value of the equality column holds about a third of the rows, so a plan that works for a rare value fails for this one. That skew is why the fix is a composite index with the equality column first.",
    ],
    figures: [
      { label: "Q1 mean before", value: ms(run.q1.mean_ms_before), source: `${run.run_id}, pg-prod, ${run.dataset.hero_table_rows.toLocaleString("en-US")} rows` },
      { label: "slow threshold", value: `${run.q1.slow_threshold_ms} ms`, source: "config.yaml workload.slow_query_ms, human-approved 2026-10-03 (the doc's 500 ms would never log Q1 at this size)" },
      { label: "hero table on disk", value: `${run.dataset.hero_table_size_mb} MB`, source: run.run_id },
      { label: "rows held by the skewed value", value: "30.01%", source: "db/NOTES.md, 2026-10-03, synthetic demo data" },
      { label: "Q1 replay medians across runs", value: "182.5 to 230.4 ms", source: "gateway/NOTES.md, 2026-10-03: 26% apart on one loaded machine, which is why every speedup is a median" },
    ],
    status: [
      { state: "REAL", text: "Synthetic demo database at 10,000,000 hero-table rows, generator and workload runner in db/." },
      { state: "SIMPLIFIED", text: "Production here is our own synthetic database, so its names and values are not secret in practice; the pipeline treats them as if they were." },
    ],
    failures: [
      ["A threshold too high never logs the hero query", "Threshold set from a measured median, approved by a human"],
      ["Cold first runs distort timings", "Warm runs and medians of 5 before any number is shown"],
    ],
    sources: "docs/architecture.md (Architecture at a glance, Demo database), db/NOTES.md, gateway/NOTES.md",
  },

  gateway: {
    heading: "The gateway hashes every name and strips every value before anything leaves",
    lead: "The gateway is plain code, not AI, and the only process that touches raw data. It is the one door between the private network and the AI zone.",
    steps: [
      "Parse each query with sqlglot (a parse tree, not regular expressions) and replace every table and column name with an HMAC-SHA256 code: t_ or c_ plus the first 8 hex characters.",
      "Replace every literal, parameter and comment with ?. If the output still holds anything that is not a code, a keyword or ?, nothing is sent (fail closed).",
      "Read plans from auto_explain: keep node types, estimated and actual rows and times; hash names and strip filters.",
      "Read pg_stats: keep distinct counts and null fractions, drop most-common values and histogram bounds (they are real values), send one skew score instead.",
      "Attach role flags to each column: primary key, foreign key, indexed, nullable from the catalog; equality, range and join use from the workload.",
      "Round row counts and sizes to 2 significant figures.",
      "Scan every outgoing payload for 20 planted canary placements, exactly and by any 6-character fragment, and record it in a ledger with its size and SHA-256. A hit blocks the payload.",
    ],
    sent: ["Query shape: which column is compared with =, with >=, joined, grouped", "Row counts and sizes, rounded to 2 significant figures", "Column role flags", "How often each template runs, as weights"],
    never: ["Any value: filter values, dates, row contents", "Table and column names (codes only)", "pg_stats value lists", "The DBA's question (mapped to template codes inside the gateway)"],
    figures: [
      { label: "outbound payloads", value: String(run.privacy.payloads), source: `${run.run_id}, payload ledger` },
      { label: "payloads to the LLM", value: String(run.privacy.llm_payloads), source: run.run_id },
      { label: "canary hits", value: `${run.privacy.canary_hits} of ${run.privacy.canaries_planted}`, source: `${run.run_id}; ${distinctCanaries} distinct values, the two filter placements reuse row values (db/canaries.py)` },
      { label: "code space at 8 hex", value: (16 ** CONFIG.hexChars).toLocaleString("en-US"), source: `16^${CONFIG.hexChars}, config.yaml hashing.hmac_code_hex_chars; about a 1 in 100,000 chance that 300 names collide (docs/architecture.md)` },
    ],
    status: [
      { state: "REAL", text: "Hashing, stripping, ingestion, ledger, canary scan, negative control and resolver (gateway/)." },
      { state: "SIMPLIFIED", text: "The adversarial leak test (a second LLM guessing names from the payloads) is built and unit-tested, but has no live score yet: the free LLM quota ran out." },
    ],
    failures: [
      ["Values leak through plan filter lines and comments", "Strip with the sqlglot parse tree, scan for canaries on every payload"],
      ["Outsiders hash common names and compare codes", "HMAC with a secret key: a guess cannot be checked without it"],
      ["Two names get the same code", "At least 8 hex characters per code"],
      ["sqlglot cannot parse a query", "Fail closed: logged as unparsed, never sent raw"],
      ["A zero canary count could mean a broken scanner", "Negative control: the same scan with hashing off finds the canaries"],
    ],
    sources: "docs/architecture.md (Threat model, Component 1, Component 7 Proof 3), gateway/strip.py, gateway/hashing.py, gateway/ingest/stats.py, db/canaries.py",
  },

  miner: {
    heading: "FP-Growth finds the column pairs that slow queries filter on together",
    lead: "Each hashed query is a shopping basket of column-and-role items. Frequent itemsets, weighted by time, become candidate indexes for the search.",
    steps: [
      "Items are column code plus role, for example c_b29c03f5:EQ and c_d81e6b44:RANGE.",
      "Each basket is weighted by total time (calls x mean ms), so one slow query outweighs a hundred fast ones.",
      "FP-Growth (mlxtend) finds column sets that appear together; support is recomputed as a share of total time.",
      "Each frequent set on one table becomes a candidate: equality columns first, then join, then range, then order; at most 3 columns.",
      "Candidates already covered by an existing index are dropped.",
      "Per time window the miner also tracks each template's share of time. A Jensen-Shannon distance above 0.2 for 2 windows in a row is drift, and triggers the search again.",
    ],
    figures: [
      { label: "Q1 recommendation", value: INDEX_COLS, source: `${run.run_id}, ${run.search.recommended_columns} columns; ${CODES_LABEL}` },
      { label: "share of slow time held by Q2", value: "about 70%", source: "miner/NOTES.md, 2026-10-03, once Q2 joined the workload" },
      { label: "drift distance, same mix", value: "0.0206", source: "miner/NOTES.md live test, 2026-10-03" },
      { label: "drift distance after the switch", value: "0.3937, then 0.4413", source: "miner/NOTES.md, 2026-10-03; triggered at the second window, threshold 0.2 (config.yaml miner.drift_js_threshold)" },
    ],
    status: [
      { state: "REAL", text: "FP-Growth over hashed templates and Jensen-Shannon drift (miner/)." },
      { state: "SIMPLIFIED", text: "Covered-index check knows primary keys only: column metadata says whether a column is indexed, not which composite index holds it." },
    ],
    failures: [
      ["Too many candidates", "Minimum support, at most 3 columns, keep the top 30"],
      ["Cheap frequent queries dominate", "Weight baskets by total time, not count"],
      ["Drift false alarms from normal noise", "Trigger only after 2 windows in a row"],
    ],
    sources: "docs/architecture.md (Component 2), miner/NOTES.md",
  },

  gnn: {
    heading: "Serving today: Postgres cost x calibration, while the GNN waits for scored weights",
    lead: "The search needs a runtime for plans that have never run, like a hypothetical index. A plan GNN is built for that job; until its delivered weights beat the Postgres baseline, the baseline serves and every screen says so.",
    steps: [
      "Input: an estimated plan tree from EXPLAIN on a hypothetical index (HypoPG). Node features: operator type, estimated rows on a log scale, estimated cost. No names.",
      "Model: plain PyTorch attention over each node and its children, 3 layers, hidden size 128, predicting each node's own time.",
      "Serving rule: the GNN serves only when its scored median q-error is below the Postgres baseline's. Otherwise the estimator is Postgres cost x a ratio measured from the baseline plan.",
      "Per-node predictions also explain where time goes, and flag nodes where Postgres's row estimate was far off, with an ANALYZE recommendation.",
    ],
    figures: [
      { label: "predicted Q1 before", value: ms(run.search.predicted_before_ms), source: `${run.run_id}, ${run.search.estimator_label}` },
      { label: "predicted Q1 after", value: ms(run.search.predicted_after_ms), source: `${run.run_id}, same estimator` },
      { label: "median q-error, reference GNN", value: "1.892", source: "models/gnn/NOTES.md, 2026-10-03: 3,133 test plans from 17 unseen templates; reference weights, never served" },
      { label: "median q-error, gradient boosting", value: "1.786", source: "same test set (scikit-learn HistGradientBoosting)" },
      { label: "median q-error, Postgres", value: "3.266", source: "same test set" },
      { label: "p95 q-error, GNN / boosting / Postgres", value: "9.636 / 11.785 / 25.601", source: "same test set" },
    ],
    status: [
      { state: "SIMPLIFIED", text: run.search.estimator_label },
      { state: "REAL", text: "Features, export, model, scoring and serving switch (models/gnn/). Training is done by a separate trainer; those weights are not delivered." },
    ],
    failures: [
      ["The GNN does not beat a boosted-tree baseline", "Reported as measured; the better model would rank, the GNN keeps node-level explanations"],
      ["It memorises training queries", "Test split by template: every test template is unseen"],
      ["Rare predictions are far off", "p95 reported; final speedups come from the twin, never from a prediction"],
    ],
    sources: "docs/architecture.md (Component 3), models/gnn/NOTES.md",
  },

  rl: {
    heading: "Q-learning picks the set of fixes, then the twin measures the top three",
    lead: "Indexes interact: two overlapping ones are worth less than the sum of their parts. The search scores combinations, not single fixes, under a write and storage budget.",
    steps: [
      "Actions: add a mined index, apply a verified rewrite rule to one template, or stop. A partition key is scored on the twin after the search.",
      "State: the set of actions chosen so far. Every unseen pair starts optimistic (q_init 1.0) so every option is tried.",
      "Reward: predicted workload time saved, minus a write penalty per index, minus a storage penalty.",
      "Each update: Q(s,a) moves alpha of the way toward R + gamma x the best Q of the next state.",
      "The top 3 configurations are measured on the twin; the best measured one wins, not the best predicted one.",
      "On drift the Q-table is kept and learning continues with the new weights.",
    ],
    figures: [
      { label: "alpha, gamma, episodes", value: `${CONFIG.alpha}, ${CONFIG.gamma}, ${CONFIG.episodes}`, source: "config.yaml rl.*" },
      { label: "Q1 search, 10M rows", value: "120.0 to 39.3 ms predicted", source: "rl/NOTES.md, 2026-10-03: 300 episodes in about 2 s, 8 configurations costed; greedy picks the same index" },
      { label: "chosen config, measured drop", value: "0.70", source: "rl/NOTES.md, 2026-10-03, index plus two rewrites, measured on the twin on a loaded machine" },
      { label: "Q3 with monthly partitions", value: "217.8 to 46.2 ms", source: "rl/NOTES.md step 32, 2026-10-03, twin; storage +87 MB, write +0.058 ms" },
      { label: "cold search", value: "120 to 145 s", source: "rl/NOTES.md, 2026-10-03, loaded demo laptop; cached afterwards" },
    ],
    status: [
      { state: "REAL", text: "Tabular Q-learning over index and rewrite actions, top-3 twin re-check, partition step." },
      { state: "MISSING", text: "Drop-index action." },
      { state: "SIMPLIFIED", text: `${run.run_id} predates the rewrite, partition and re-check steps: its label reads "${run.search.label}".` },
    ],
    failures: [
      ["The agent exploits estimator mistakes", "Top 3 re-measured on the twin; disagreement is penalised"],
      ["Write cost is guessed during search", "Per-index penalty in search, pgbench measurement of the final choice"],
      ["Search is slow", "Costs cached per set of actions and slow templates"],
    ],
    sources: "docs/architecture.md (Component 4), rl/NOTES.md, config.yaml rl.*",
  },

  llm: {
    heading: "The LLM explains the fix, and a checker rejects any number it did not get from a tool",
    lead: "The agent is the DBA's interface. It receives only template codes, calls tools for evidence, and writes its answer in codes; the gateway turns codes back into names on the private side.",
    steps: [
      "The DBA's question is matched to template codes inside the gateway. The LLM receives the codes, never the question.",
      "The agent calls up to 8 tools (slow templates, plan, mined candidates, search, explain, rewrite candidates, verify, simulate).",
      "Rewrites come only through the gateway's rule library and are verified before they are offered.",
      "The number checker compares every number in the answer with the tool results. An answer with an unmatched number is blocked.",
      "The gateway dehashes the answer for the DBA. Every LLM request body is canary-scanned first.",
    ],
    figures: [
      { label: "model", value: run.llm.model, source: `${run.run_id}, provider ${run.llm.provider}` },
      { label: "tool calls", value: String(run.llm.tool_calls), source: `${run.run_id}; cap 8 per question (config.yaml llm.max_tool_calls)` },
      { label: "numbers checked", value: String(run.llm.numbers_checked), source: run.run_id },
      { label: "canary hits in LLM payloads", value: `${run.privacy.canary_hits} in ${run.privacy.llm_payloads}`, source: run.run_id },
    ],
    status: [
      { state: "REAL", text: "Agent, 8 tools, number checker, retries on rate limits (agent/)." },
      { state: "SIMPLIFIED", text: "Air-gapped mode with a local model: plumbing built and tested with a stand-in; the real local model is unverified." },
    ],
    failures: [
      ["The question carries real names", "Resolved to template codes inside the gateway"],
      ["The model invents a confident number", "Number checker blocks the answer"],
      ["A rewrite changes the query's result", "Rule library only, verified, never applied automatically"],
      ["The agent loops on tools", "Cap of 8 calls per question"],
    ],
    sources: "docs/architecture.md (Component 5, LLM tools and system rules), agent/NOTES.md",
  },

  twin: {
    heading: "Every speedup on this site was measured on a synthetic twin, not predicted",
    lead: "The twin is a second Postgres with the same tables and columns and fake rows generated from production's statistics. Real indexes are built there, real queries replayed, real inserts timed.",
    steps: [
      "Rows are generated from pg_stats: same row counts, distinct counts, skew and null fractions; correlation is kept for column pairs the miner flags.",
      "The chosen configuration is built on the twin and the slow templates are replayed: median of 5 warm runs before and after.",
      "Write cost: pgbench insert latency with and without the new indexes. Storage: each index's size on disk.",
      "Result checksums compare the answer before and after. Rewrites are also checked by VeriEQL, bounded to 5 rows per table.",
      "Plan agreement: production's plan shape is compared with the twin's; a mismatch blocks the number.",
    ],
    figures: [
      { label: "Q1 on the twin", value: `${ms(run.twin.before_ms)} to ${ms(run.twin.after_ms)}`, source: `${run.run_id}, median of ${run.twin.runs}, measured while plan generation loaded the CPU` },
      { label: "faster", value: `${run.twin.speedup_pct}%`, source: run.run_id },
      { label: "index size", value: `${run.twin.storage_mb} MB`, source: run.run_id },
      { label: "write cost per insert", value: `+${WRITE_COST.medianMs} ms`, source: `db/NOTES.md, 2026-10-03, median of ${WRITE_COST.runs} pgbench runs, mostly the new index being cold in cache` },
      { label: "twin fidelity Q1 / Q2 / two-region", value: "0.763 / 0.987 / 0.951", source: "db/NOTES.md, 2026-10-03, correlated twin, loaded machine; 1.0 means the twin predicts production's speedup exactly" },
      { label: "Q2 rewrite alone", value: "63.5% faster", source: "gateway/NOTES.md, 2026-10-03; on the correlated twin Q2 measures 22% to 45%" },
    ],
    status: [
      { state: "REAL", text: "Twin measurement, write cost, storage, plan agreement, checksums, HypoPG what-if (db/sandbox/)." },
      { state: "SIMPLIFIED", text: "Twin built from pg_stats with correlations only for the column pairs the miner flags." },
    ],
    failures: [
      ["Twin plans differ from production's", "Correlations kept for flagged pairs; plan agreement and fidelity reported"],
      ["Noisy timings", "Warm runs, median of 5, same machine before and after"],
      ["Checksums match on fake data but miss edge cases", "NULLs and edge values generated; VeriEQL bound stated"],
    ],
    sources: "docs/architecture.md (Component 6, Component 7), db/NOTES.md, gateway/NOTES.md, verify/NOTES.md",
  },

  dba: {
    heading: "Nothing reaches production until a DBA runs the migration by hand",
    lead: "Approval produces three files with real names, made only on the private side: a migration, a rollback, and a post-deploy check that runs the rollback if latency gets worse.",
    steps: [
      "migration.sql builds each index with CREATE INDEX CONCURRENTLY, outside a transaction, so writes are not blocked.",
      "rollback.sql drops them with DROP INDEX CONCURRENTLY IF EXISTS, last action first; it also clears an invalid index a failed build left.",
      "Rewrites appear as comments: a suggested application change with the original and rewritten query, never run by the file.",
      "post_deploy_check.py records a baseline, then after the migration replays the slow templates and runs rollback.sql if a median gets worse.",
      "The approve endpoint refuses the AI service (HTTP 403); only the operator side can ask for the files.",
    ],
    figures: [
      { label: "post-deploy check window", value: "10 min", source: "config.yaml approve.post_deploy_check_minutes" },
      { label: "rollback when a median is worse by", value: "10%", source: "config.yaml approve.rollback_if_median_worse_by (0.10)" },
    ],
    status: [
      { state: "REAL", text: "Approve, migration, rollback and post-deploy check (gateway/approve.py, gateway/post_deploy_check.py)." },
      { state: "SIMPLIFIED", text: "The dashboard demo runs the check on the twin with a shortened replay, labelled as such." },
    ],
    failures: [
      ["An index build blocks writes", "CONCURRENTLY, never inside a transaction"],
      ["A change makes things worse after deploy", "Post-deploy check runs the rollback by itself"],
      ["The AI side asks for files with real names", "403 for the ai service"],
    ],
    sources: "docs/architecture.md (Component 8, Approve and deploy), gateway/NOTES.md, gateway/approve.py",
  },
};
