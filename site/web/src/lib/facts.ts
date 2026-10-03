// Every figure the playground shows, with its source. The run record is an exact copy of
// runs/latest.json (gitignored, so copied here). Anything not in it names its own source.
import run from "@/data/run_d1b30d38.json";

export { run };

// config.yaml at commit 539e395. Copied, not read at runtime: the browser cannot read config.yaml.
export const CONFIG = {
  alpha: 0.1, // rl.alpha
  gamma: 0.9, // rl.gamma
  qInit: 1.0, // rl.q_init
  episodes: 300, // rl.episodes
  hexChars: 8, // hashing.hmac_code_hex_chars
};

// Public pages never show the demo database's real names (scripts/tests/test_export_and_site.py
// REAL). Every query below uses one illustrative code map, labelled on screen with CODES_LABEL.
// Real codes are t_ or c_ plus the first 8 hex of HMAC-SHA256 under the key in .env.
export const CODES_LABEL = "illustrative codes, not the gateway's real ones";
export const CODE = { table: "t_7a3f91c2", sum: "c_4e1d9a07", eq: "c_b29c03f5", range: "c_d81e6b44" };
export const INDEX_COLS = `(${CODE.eq}, ${CODE.range})`;

// Q1 as the AI side receives it: names hashed (gateway/hashing.py), values as ? (gateway/strip.py).
export const Q1_HASHED = `SELECT SUM(${CODE.sum}) FROM ${CODE.table} WHERE ${CODE.eq} = ? AND ${CODE.range} >= ?`;

// db/workload.py QOR_TEMPLATE in the same codes, and rule or_same_column_to_in
// (gateway/rewrite_rules.py) applied by hand (exact sqlglot output not captured). Verified by VeriEQL.
export const QOR_SQL = `SELECT SUM(${CODE.sum})\nFROM ${CODE.table}\nWHERE (${CODE.eq} = ? OR ${CODE.eq} = ?)\n  AND ${CODE.range} >= ?`;
export const QOR_REWRITTEN = `SELECT SUM(${CODE.sum})\nFROM ${CODE.table}\nWHERE ${CODE.eq} IN (?, ?)\n  AND ${CODE.range} >= ?`;

// db/NOTES.md 2026-10-03: Q1 index on the 10M twin, 6 pgbench runs on a loaded machine.
export const WRITE_COST = { medianMs: 0.032, runs: 6, baseLo: 0.23, baseHi: 0.51 };

// db/canaries.py PLACEMENTS: id = cn_ + first 8 hex of SHA-256 of the value. Values are never shown.
export const CANARIES: [string, string, string][] = [
  ["cn_2b631864", "customer_email", "planted in a pg-prod row"],
  ["cn_e2058b34", "customer_email", "planted in a pg-prod row"],
  ["cn_6b1c58c0", "customer_email", "planted in a pg-prod row"],
  ["cn_5ef352d0", "customer_email", "planted in a pg-prod row"],
  ["cn_5a5634ea", "customer_email", "planted in a pg-prod row"],
  ["cn_829b28b3", "customer_name", "planted in a pg-prod row"],
  ["cn_2a5b4dc5", "customer_name", "planted in a pg-prod row"],
  ["cn_4c8b5451", "customer_name", "planted in a pg-prod row"],
  ["cn_4be406c7", "customer_phone", "planted in a pg-prod row"],
  ["cn_a31434da", "customer_phone", "planted in a pg-prod row"],
  ["cn_b71f520d", "sale_amount", "planted in a pg-prod row"],
  ["cn_60dba5fe", "sale_amount", "planted in a pg-prod row"],
  ["cn_b6fd4a4b", "sale_amount", "planted in a pg-prod row"],
  ["cn_ff099b6d", "product_name", "planted in a pg-prod row"],
  ["cn_894f29f2", "product_name", "planted in a pg-prod row"],
  ["cn_cd952109", "query_comment", "sent as a SQL comment on a logged query"],
  ["cn_41219be8", "query_comment", "sent as a SQL comment on a logged query"],
  ["cn_2b631864", "customer_email", "used as a filter value in a logged query"],
  ["cn_829b28b3", "customer_name", "used as a filter value in a logged query"],
  ["cn_e2ef58f4", "dba_question", "typed into a DBA question"],
];

// agent/tools.py DECLARATIONS: names and parameter schemas verbatim; descriptions verbatim except
// run_rl and verify, where one verb is reworded (it is on the public forbidden-word list).
export const TOOLS: { name: string; description: string; parameters: object }[] = [
  { name: "get_slow_templates", description: "Top query templates by total time, hashed.", parameters: { type: "object", properties: {} } },
  { name: "get_plan", description: "Latest executed plan of one template, with measured per-node times.", parameters: { type: "object", properties: { template_id: { type: "string" } }, required: ["template_id"] } },
  { name: "mine_candidates", description: "Candidate indexes mined from the slow workload, with support.", parameters: { type: "object", properties: {} } },
  { name: "run_rl", description: "Search for the best configuration of index and rewrite actions. Gives back a config_id, its actions and predicted times; the final pick is the best measured on the twin of the top few. A partition action (monthly ranges) is measured on the twin only and has no predicted time.", parameters: { type: "object", properties: { template_ids: { type: "array", items: { type: "string" } } } } },
  { name: "gnn_explain", description: "Why one template's latest plan is slow: the plan nodes with the largest predicted share of time (from the serving runtime estimator), and nodes where Postgres's row estimate was off by the alert ratio or more, with an ANALYZE recommendation.", parameters: { type: "object", properties: { template_id: { type: "string" } }, required: ["template_id"] } },
  { name: "rewrite_candidates", description: "Rewrite rules that fit each slow template's shape, with the rewritten hashed SQL (values shown as ?). Not yet checked.", parameters: { type: "object", properties: {} } },
  { name: "verify", description: "Check one rewrite: the gateway applies the rule to the real query and runs an equivalence verifier and a result checksum on the twin. Gives status Verified, TestedOnly or Rejected.", parameters: { type: "object", properties: { template_id: { type: "string" }, rule_id: { type: "string" } }, required: ["template_id", "rule_id"] } },
  { name: "simulate", description: "Measure a configuration on the statistical twin: before and after ms, storage MB.", parameters: { type: "object", properties: { config_id: { type: "string" } }, required: ["config_id"] } },
];

// gateway/approve.py build() for one add_index action, rendered by hand in the illustrative codes
// (the real files carry real names and are made only on the operator side). The run record does
// not keep the config_id or the search name, so those stay marked.
const RUN_LINE = (f: string) =>
  `-- Run with: psql -v ON_ERROR_STOP=1 -f ${f}  (no BEGIN/COMMIT and no --single-transaction: CONCURRENTLY cannot run in a transaction block)`;
const IDX = `bt_${CODE.table}_${CODE.eq}_${CODE.range}`;
export const MIGRATION_SQL = [
  "-- Tiresias migration for <config_id not in run record> (search: <not in run record>).",
  RUN_LINE("migration.sql"),
  "-- Before it: python post_deploy_check.py baseline. After it: python post_deploy_check.py check.",
  `-- 1. add_index on ${CODE.table} ${INDEX_COLS}`,
  `CREATE INDEX CONCURRENTLY "${IDX}" ON "${CODE.table}" ("${CODE.eq}", "${CODE.range}");`,
  "",
].join("\n");
export const ROLLBACK_SQL = [
  "-- Tiresias rollback for <config_id not in run record>: undoes migration.sql, last action first.",
  RUN_LINE("rollback.sql"),
  "-- post_deploy_check.py check runs this file itself when a template's median latency gets worse.",
  "-- undo 1: drop the index migration.sql created (IF EXISTS: also clears an invalid index a failed build left)",
  `DROP INDEX CONCURRENTLY IF EXISTS "${IDX}";`,
  "",
].join("\n");

export const ms = (x: number) => `${x.toFixed(1)} ms`;
