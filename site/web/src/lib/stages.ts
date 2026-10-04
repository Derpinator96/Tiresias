// The 8 pipeline stages and the copy of their pages. Plain module (no "use client"), so server
// pages can read it. Every figure carries its source and, where it rests on one, its assumption.
// Copy comes from docs/architecture.md (components 1 to 8) and the NOTES.md files, with the demo
// database's real names left out (public pages never show them).
import { ClipboardCheck, Cpu, Database, FlaskConical, Grid3x3, MessageSquareCode, Pickaxe, ShieldCheck } from "lucide-react";
import { CANARIES, CODES_LABEL, CONFIG, GNN_SERVING, INDEX_COLS, WRITE_COST, run, writeShare } from "@/lib/facts";
import measurements from "@/data/measurements.json";

const [GNN_M, GBT_M, PG_M] = measurements.gnn.models;

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

/** One icon per stage (sidebar, overview map, playground cards). Stages carry no numbers on screen. */
export const STAGE_ICON: Record<StageId, typeof Database> = {
  source: Database, gateway: ShieldCheck, miner: Pickaxe, gnn: Cpu, rl: Grid3x3, llm: MessageSquareCode, twin: FlaskConical, dba: ClipboardCheck,
};

/** Zone tint per stage (plan section 5): private source and gateway leaf, AI stages each their own
 *  pastel, twin and DBA sky. Full class names so Tailwind finds them. */
export const STAGE_TINT: Record<StageId, { bg: string; soft: string; ink: string }> = {
  source: { bg: "bg-leaf", soft: "bg-leaf/40", ink: "text-leaf-ink" },
  gateway: { bg: "bg-leaf", soft: "bg-leaf/40", ink: "text-leaf-ink" },
  miner: { bg: "bg-sand", soft: "bg-sand/40", ink: "text-sand-ink" },
  gnn: { bg: "bg-sky", soft: "bg-sky/40", ink: "text-sky-ink" },
  rl: { bg: "bg-peach", soft: "bg-peach/40", ink: "text-peach-ink" },
  llm: { bg: "bg-rose", soft: "bg-rose/40", ink: "text-rose-ink" },
  twin: { bg: "bg-sky", soft: "bg-sky/40", ink: "text-sky-ink" },
  dba: { bg: "bg-sky", soft: "bg-sky/40", ink: "text-sky-ink" },
};

export const STAGE_SUMMARY: Record<StageId, string> = {
  source: "Postgres logs the slow query shape; values are already $1.",
  gateway: "Hashes names, strips values, scans every payload for canaries.",
  miner: "FP-Growth over hashed queries proposes composite indexes.",
  gnn: "Estimates runtimes of plans that never ran; Postgres baseline serves until the GNN is scored.",
  rl: "Q-learning picks the best set of fixes under a write and storage budget.",
  llm: "Explains the fix in plain words; every number is checked.",
  twin: "Measures the fix on a synthetic copy, never on production.",
  dba: "Signed-off migration and rollback; the DBA runs them by hand.",
};

export type Figure = { label: string; value: string; source: string };
export type Status = { state: "REAL" | "SIMPLIFIED" | "PLACEHOLDER" | "MISSING"; text: string };
export type StageCopy = {
  heading: string; // states a fact, under 8 words
  steps: string[]; // one clause each
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
    heading: "Postgres logs the slow query without values",
    steps: [
      "pg_stat_statements groups queries by shape; values are already $1, $2.",
      "auto_explain logs the plan of any query over the threshold.",
      "Q1 sums one column for one equality value and a date range.",
      "One value holds a third of the rows, so the index leads with it.",
    ],
    figures: [
      { label: "Q1 mean before", value: ms(run.q1.mean_ms_before), source: `${run.run_id}, pg-prod, ${run.dataset.hero_table_rows.toLocaleString("en-US")} rows` },
      { label: "slow threshold", value: `${run.q1.slow_threshold_ms} ms`, source: "config.yaml workload.slow_query_ms, human-approved 2026-10-03" },
      { label: "hero table on disk", value: `${run.dataset.hero_table_size_mb} MB`, source: run.run_id },
      { label: "rows held by the skewed value", value: "30.01%", source: "db/NOTES.md, 2026-10-03, synthetic data" },
      { label: "Q1 replay medians across runs", value: "182.5 to 230.4 ms", source: "gateway/NOTES.md, 2026-10-03: 26% apart on one loaded machine" },
    ],
    status: [
      { state: "REAL", text: "Synthetic database, 10,000,000 hero-table rows (db/)." },
      { state: "SIMPLIFIED", text: "Production is our own synthetic database; treated as secret anyway." },
    ],
    failures: [
      ["A threshold too high never logs the hero query", "Threshold from a measured median, human-approved"],
      ["Cold first runs distort timings", "Warm runs, median of 5"],
    ],
    sources: "docs/architecture.md, db/NOTES.md, gateway/NOTES.md",
  },

  gateway: {
    heading: "Names hashed, values stripped, before anything leaves",
    steps: [
      "sqlglot parses each query; names become HMAC-SHA256 codes (t_, c_ + 8 hex).",
      "Literals, parameters and comments become ?; anything else fails closed.",
      "Plans keep node types, rows and times; names hashed, filters stripped.",
      "pg_stats keeps distinct counts and null fractions; values become a skew score.",
      "Column role flags: pk, fk, indexed, nullable, equality, range, join.",
      "Row counts and sizes rounded to 2 significant figures.",
      "Every payload canary-scanned and logged in a ledger; a hit blocks it.",
    ],
    sent: ["Query shape: which column is compared with =, >=, joined, grouped", "Row counts and sizes, 2 significant figures", "Column role flags", "Template run frequency, as weights"],
    never: ["Any value: filters, dates, row contents", "Table and column names (codes only)", "pg_stats value lists", "The DBA's question (resolved to template codes inside the gateway)"],
    figures: [
      { label: "outbound payloads", value: String(run.privacy.payloads), source: `${run.run_id}, payload ledger` },
      { label: "payloads to the LLM", value: String(run.privacy.llm_payloads), source: run.run_id },
      { label: "canary hits", value: `${run.privacy.canary_hits} of ${run.privacy.canaries_planted}`, source: `${run.run_id}; ${distinctCanaries} distinct values, two placements reuse row values (db/canaries.py)` },
      { label: "code space at 8 hex", value: (16 ** CONFIG.hexChars).toLocaleString("en-US"), source: `16^${CONFIG.hexChars}, config.yaml hashing.hmac_code_hex_chars; about 1 in 100,000 that 300 names collide` },
    ],
    status: [
      { state: "REAL", text: "Hashing, stripping, ledger, canary scan, resolver (gateway/)." },
      { state: "SIMPLIFIED", text: "Adversarial leak test built, no live score (LLM quota)." },
    ],
    failures: [
      ["Values leak through plan filters and comments", "Strip on the parse tree; canary scan on every payload"],
      ["Outsiders hash common names and compare codes", "HMAC with a secret key"],
      ["Two names get the same code", "At least 8 hex characters per code"],
      ["sqlglot cannot parse a query", "Fail closed: logged as unparsed, never sent"],
      ["A zero canary count could mean a broken scanner", "Negative control: the scan with hashing off finds them"],
    ],
    sources: "docs/architecture.md, gateway/strip.py, gateway/hashing.py, gateway/ingest/stats.py, db/canaries.py",
  },

  miner: {
    heading: "FP-Growth finds columns filtered together",
    steps: [
      "Items: column code plus role, for example c_b29c03f5:EQ.",
      "Baskets weighted by total time (calls x mean ms).",
      "FP-Growth (mlxtend) finds frequent column sets; support as share of time.",
      "Each set becomes a candidate: equality, join, range, order; at most 3 columns.",
      "Candidates covered by an existing index are dropped.",
      "Drift: Jensen-Shannon distance above 0.2 for 2 windows re-runs the search.",
    ],
    figures: [
      { label: "Q1 recommendation", value: INDEX_COLS, source: `${run.run_id}, ${run.search.recommended_columns} columns; ${CODES_LABEL}` },
      { label: "share of slow time held by Q2", value: "about 70%", source: "miner/NOTES.md, 2026-10-03" },
      { label: "drift distance, same mix", value: "0.0206", source: "miner/NOTES.md live test, 2026-10-03" },
      { label: "drift distance after the switch", value: "0.3937, then 0.4413", source: "miner/NOTES.md, 2026-10-03; threshold 0.2 (config.yaml miner.drift_js_threshold)" },
    ],
    status: [
      { state: "REAL", text: "FP-Growth over hashed templates and drift (miner/)." },
      { state: "SIMPLIFIED", text: "Covered-index check knows primary keys only." },
    ],
    failures: [
      ["Too many candidates", "Minimum support, at most 3 columns, top 30"],
      ["Cheap frequent queries dominate", "Baskets weighted by time, not count"],
      ["Drift false alarms", "Trigger only after 2 windows in a row"],
    ],
    sources: "docs/architecture.md, miner/NOTES.md",
  },

  gnn: {
    heading: "The trained GNN serves: it beats Postgres's own estimate",
    steps: [
      "Input: EXPLAIN plan tree on a HypoPG index; operator, rows, cost; no names.",
      "Model: PyTorch attention over node and children, 3 layers, hidden 128.",
      "Serves only when its median q-error beats the Postgres baseline.",
      "Per-node predictions flag bad row estimates with an ANALYZE recommendation.",
    ],
    figures: [
      { label: "predicted Q1 before", value: ms(run.search.predicted_before_ms), source: `${run.run_id}, ${run.search.estimator_label}` },
      { label: "predicted Q1 after", value: ms(run.search.predicted_after_ms), source: `${run.run_id}, same estimator` },
      { label: "median q-error, GNN (serving)", value: String(GNN_M.median), source: "models/gnn/results.json, 2026-10-03: 3,133 test plans, 17 unseen templates" },
      { label: "median q-error, gradient boosting", value: String(GBT_M.median), source: "same test set (scikit-learn HistGradientBoosting)" },
      { label: "median q-error, Postgres", value: String(PG_M.median), source: "same test set" },
      { label: "p95 q-error, GNN / boosting / Postgres", value: `${GNN_M.p95} / ${GBT_M.p95} / ${PG_M.p95}`, source: "same test set" },
    ],
    status: [
      { state: "REAL", text: `${GNN_SERVING}; Postgres cost x calibration is the fallback. ${run.run_id} predates it (${run.search.estimator_label}).` },
      { state: "REAL", text: "Features, export, model, scoring, serving switch (models/gnn/)." },
    ],
    failures: [
      ["The GNN does not beat boosted trees", "Reported as measured; the better model would rank"],
      ["It memorises training queries", "Test split by template: every test template unseen"],
      ["Rare predictions are far off", "p95 reported; speedups come from the twin, never a prediction"],
    ],
    sources: "docs/architecture.md, models/gnn/NOTES.md",
  },

  rl: {
    heading: "Q-learning picks fixes, the twin measures three",
    steps: [
      "Actions: add a mined index, apply a verified rewrite, or stop.",
      "State: the actions chosen so far; unseen pairs start at q_init 1.0.",
      "Reward: predicted time saved minus write and storage penalties.",
      "Update: Q(s,a) moves alpha toward R + gamma x best next Q.",
      "Top 3 configurations measured on the twin; best measured wins.",
      "On drift the Q-table is kept and learning continues.",
    ],
    figures: [
      { label: "alpha, gamma, episodes", value: `${CONFIG.alpha}, ${CONFIG.gamma}, ${CONFIG.episodes}`, source: "config.yaml rl.*" },
      { label: "Q1 search, 10M rows", value: "120.0 to 39.3 ms predicted", source: "rl/NOTES.md, 2026-10-03: 300 episodes in about 2 s, 8 configurations costed" },
      { label: "chosen config, measured drop", value: "0.70", source: "rl/NOTES.md, 2026-10-03, index plus two rewrites, twin, loaded machine" },
      { label: "Q3 with monthly partitions", value: "217.8 to 46.2 ms", source: "rl/NOTES.md step 32, measured once on the twin 2026-10-03; storage +87 MB, write +0.058 ms. Off on the demo laptop: rl.partition_max_keys 0 (human decision 2026-10-04)" },
      { label: "cold search", value: "120 to 145 s", source: "rl/NOTES.md, 2026-10-03, loaded laptop; cached afterwards" },
    ],
    status: [
      { state: "REAL", text: "Tabular Q-learning, top-3 twin re-check." },
      { state: "SIMPLIFIED", text: "Partition step built and tested (rl/tests/test_partition.py) but off on the demo laptop: a cold search ran past 300 s." },
      { state: "MISSING", text: "Drop-index action." },
      { state: "SIMPLIFIED", text: `${run.run_id} predates rewrites and re-check: "${run.search.label}".` },
    ],
    failures: [
      ["The agent exploits estimator mistakes", "Top 3 re-measured on the twin"],
      ["Write cost is guessed during search", "Per-index penalty, then pgbench on the final choice"],
      ["Search is slow", "Costs cached per set of actions and slow templates"],
    ],
    sources: "docs/architecture.md, rl/NOTES.md, config.yaml rl.*",
  },

  llm: {
    heading: "The LLM explains; a checker rejects unsourced numbers",
    steps: [
      "The question resolves to template codes inside the gateway.",
      "The agent calls up to 8 tools for evidence.",
      "Rewrites come only from the verified rule library.",
      "Every number in the answer must match a tool result.",
      "The gateway dehashes the answer; every request body is canary-scanned.",
    ],
    figures: [
      { label: "model", value: run.llm.model, source: `${run.run_id}, provider ${run.llm.provider}` },
      { label: "tool calls", value: String(run.llm.tool_calls), source: `${run.run_id}; cap 8 (config.yaml llm.max_tool_calls)` },
      { label: "numbers checked", value: String(run.llm.numbers_checked), source: run.run_id },
      { label: "canary hits in LLM payloads", value: `${run.privacy.canary_hits} in ${run.privacy.llm_payloads}`, source: run.run_id },
    ],
    status: [
      { state: "REAL", text: "Agent, 8 tools, number checker, retries (agent/)." },
      { state: "SIMPLIFIED", text: "Air-gapped mode tested with a stand-in model only." },
    ],
    failures: [
      ["The question carries real names", "Resolved to codes inside the gateway"],
      ["The model invents a number", "Number checker blocks the answer"],
      ["A rewrite changes the result", "Rule library only, verified, never applied automatically"],
      ["The agent loops on tools", "Cap of 8 calls per question"],
    ],
    sources: "docs/architecture.md, agent/NOTES.md",
  },

  twin: {
    heading: "Every speedup measured on a synthetic twin",
    steps: [
      "Rows generated from pg_stats; correlation kept for flagged column pairs.",
      "Configuration built on the twin; median of 5 warm runs before and after.",
      "Write cost: pgbench inserts with and without the indexes.",
      "Result checksums before and after; rewrites also VeriEQL-checked (5 rows).",
      "Plan agreement: a shape mismatch with production blocks the number.",
    ],
    figures: [
      { label: "Q1 on the twin", value: `${ms(run.twin.before_ms)} to ${ms(run.twin.after_ms)}`, source: `${run.run_id}, median of ${run.twin.runs}, CPU loaded by plan generation` },
      { label: "faster", value: `${run.twin.speedup_pct}%`, source: run.run_id },
      { label: "index size", value: `${run.twin.storage_mb} MB`, source: run.run_id },
      { label: "write cost per insert", value: `+${WRITE_COST.medianMs} ms, ${writeShare(WRITE_COST.medianMs)}`, source: `db/NOTES.md, 2026-10-03, median of ${WRITE_COST.runs} pgbench runs, cold index; the insert range is the same runs without the index` },
      { label: "twin fidelity Q1 / Q2 / two-region", value: "0.763 / 0.987 / 0.951", source: "db/NOTES.md, 2026-10-03, correlated twin, loaded machine; 1.0 is exact" },
      { label: "Q2 rewrite alone", value: "63.5% faster", source: "gateway/NOTES.md, 2026-10-03; correlated twin 22% to 45%" },
    ],
    status: [
      { state: "REAL", text: "Twin measurement, write cost, checksums, HypoPG (db/sandbox/)." },
      { state: "SIMPLIFIED", text: "Twin from pg_stats; correlations only for flagged pairs." },
    ],
    failures: [
      ["Twin plans differ from production's", "Correlations for flagged pairs; fidelity reported"],
      ["Noisy timings", "Warm runs, median of 5, same machine"],
      ["Checksums miss edge cases", "NULLs and edge values generated; VeriEQL bound stated"],
    ],
    sources: "docs/architecture.md, db/NOTES.md, gateway/NOTES.md, verify/NOTES.md",
  },

  dba: {
    heading: "A DBA runs the migration by hand",
    steps: [
      "migration.sql: CREATE INDEX CONCURRENTLY, outside a transaction.",
      "rollback.sql: DROP INDEX CONCURRENTLY IF EXISTS, last action first.",
      "Rewrites appear as comments, never run by the file.",
      "post_deploy_check.py replays the templates and rolls back if a median worsens.",
      "The approve endpoint refuses the AI service (HTTP 403).",
    ],
    figures: [
      { label: "post-deploy check window", value: "10 min", source: "config.yaml approve.post_deploy_check_minutes" },
      { label: "rollback when a median is worse by", value: "10%", source: "config.yaml approve.rollback_if_median_worse_by" },
    ],
    status: [
      { state: "REAL", text: "Approve, migration, rollback, post-deploy check (gateway/approve.py)." },
      { state: "SIMPLIFIED", text: "Demo check runs on the twin with a shortened replay." },
    ],
    failures: [
      ["An index build blocks writes", "CONCURRENTLY, never inside a transaction"],
      ["A change is worse after deploy", "Post-deploy check runs the rollback itself"],
      ["The AI side asks for files with real names", "403 for the ai service"],
    ],
    sources: "docs/architecture.md, gateway/NOTES.md, gateway/approve.py",
  },
};
