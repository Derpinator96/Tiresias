import { test } from "node:test";
import assert from "node:assert/strict";
import { viewOf, actionWords } from "../src/lib/run-view.ts";
import run from "../src/data/run_d1b30d38.json" with { type: "json" };

const fb = { run, table: "t_aaaaaaaa", columns: ["c_bbbbbbbb", "c_cccccccc"], sql: "SELECT ?", migration: "-- m", rollback: "-- r", writeCostMs: 0.032, writeCostSource: "db/NOTES.md", codesLabel: "illustrative codes" };

// A small fake bundle (shape: src/lib/bundle.ts). Codes and names are invented for the test.
const bundle = {
  id: "qn_test0001", question: "why is the weekly report slow", created_at: "2026-10-04T10:00:00Z", template_ids: ["q_11111111"],
  job: { question_id: "qn_test0001", template_ids: ["q_11111111"], done: true, ask: { status: 200, checker: "ok", hashed: "add an index on t_22222222", real: "add an index on big_table", tool_calls: 4 }, migration: "CREATE INDEX x ON big_table (k, d);", rollback: "DROP INDEX x;" },
  events: ["tool get_slow_templates", "tool run_rl"],
  llm: { provider: "gemini", model: "gemini-test", seconds: 12.5, tool_calls: 4 },
  estimator: { estimator: "postgres", label: "estimator: Postgres cost x calibration (GNN pending)" },
  slow: [{ template_id: "q_99999999", sql: "SELECT ? FROM t_33333333", calls: 1, mean_ms: 5, total_ms: 5, columns: [] }, { template_id: "q_11111111", sql: "SELECT SUM(c_44444444) FROM t_22222222 WHERE c_55555555 = ?", calls: 10, mean_ms: 200, total_ms: 2000, columns: [] }],
  plans: {}, predictions: {}, explain: {},
  mine: { candidates: [{ cand_id: "cd_1", table: "t_22222222", columns: ["c_55555555", "c_66666666"], support: 0.9, evidence: { items: [], templates: [] } }] },
  rl: { config: { config_id: "cfg_1", search: "qlearning", actions: [] }, label: "search: Q-learning", estimator_label: "estimator: test", baseline_predicted_ms: 100, final_predicted_ms: 25, steps: 1, configs_costed: 1, cache_hits: 0, episodes: 1, top_configs: [], greedy: null, rewrites: [], final_choice: "x", partition: null, q_entries: 1 },
  config: { config_id: "cfg_1", search: "qlearning", actions: [{ type: "add_index", table: "t_22222222", columns: ["c_55555555", "c_66666666"] }, { type: "rewrite", template_id: "q_11111111", rule_id: "or_same_column_to_in" }] },
  sim: { config_id: "cfg_1", source: "twin", templates: [{ template_id: "q_11111111", before_ms: 300, after_ms: 75 }], write_ms_delta: null, storage_mb_delta: 68, runs: 5 },
  hypopg: null,
  ledger: { before: { outbound_payloads: 100, outbound_canary_hits: 1, outbound_blocked: 0, canaries_planted: 20 }, after: { outbound_payloads: 143, outbound_canary_hits: 1, outbound_blocked: 2, canaries_planted: 20 } },
  tables: [{ table: "t_33333333", rows: 50000000, size_mb: 4000, writes_per_s: 1 }, { table: "t_22222222", rows: 10000000, size_mb: 940, writes_per_s: 3 }],
  names: { t_22222222: "big_table", "c_55555555": "big_table.k", "c_66666666": "big_table.d", q_11111111: "SELECT SUM(v) FROM big_table WHERE k = 7" },
};

test("bundle: derived figures", () => {
  const v = viewOf(bundle, fb);
  assert.equal(v.live, true);
  assert.equal(v.id, "qn_test0001");
  assert.equal(v.payloads, 43);
  assert.equal(v.canaryHits, 0);
  assert.equal(v.blocked, 2);
  assert.equal(v.canariesPlanted, 20);
  assert.equal(v.meanBefore, 200); // the resolved template, not slow[0]
  assert.equal(v.templateSqlReal, "SELECT SUM(v) FROM big_table WHERE k = 7");
  assert.equal(v.twinBefore, 300);
  assert.equal(v.speedupPct, 75);
  assert.equal(v.storageMb, 68);
  assert.equal(v.heroTable, "big_table"); // the indexed table, not the largest
  assert.equal(v.heroRows, 10000000);
  assert.equal(v.indexCols, "(k, d)");
  assert.equal(v.recommendedColumns, 2);
  assert.deepEqual(v.actions, ["add index on big_table (k, d)", "rewrite q_11111111 with rule or_same_column_to_in"]);
  assert.deepEqual(v.candidates, [{ table: "big_table", columns: ["k", "d"], support: 0.9 }]);
  assert.equal(v.predictedBefore, 100);
  assert.equal(v.predictedAfter, 25);
  assert.equal(v.llm.toolCalls, 4);
  assert.equal(v.llm.seconds, 12.5);
  assert.equal(v.llm.checker, "ok");
  assert.equal(v.llmPayloads, null);
  assert.equal(v.answer.real, "add an index on big_table");
  assert.equal(v.migration, "CREATE INDEX x ON big_table (k, d);");
  assert.equal(v.slowThresholdMs, run.q1.slow_threshold_ms);
  assert.match(v.src.threshold, /not in the bundle/);
  assert.equal(v.checksumMatch, run.twin.checksum_match);
  assert.match(v.src.checksum, /run_d1b30d38/);
  assert.equal(v.writeCostMs, 0.032); // sim.write_ms_delta is null: the facts value, labelled
  assert.match(v.src.writeCost, /not in the bundle/);
  assert.match(v.src.twin, /qn_test0001.*median of 5/);
});

test("bundle without a search run or twin result", () => {
  const v = viewOf({ ...bundle, rl: null, sim: null, config: null, mine: null, llm: null, tables: [] }, fb);
  assert.equal(v.predictedBefore, run.search.predicted_before_ms);
  assert.match(v.src.predicted, /no search run/);
  assert.equal(v.twinBefore, null);
  assert.equal(v.speedupPct, null);
  assert.deepEqual(v.actions, []);
  assert.equal(v.heroTable, null);
  assert.equal(v.llm.model, "none");
});

test("null bundle: the run record and facts", () => {
  const v = viewOf(null, fb);
  assert.equal(v.live, false);
  assert.equal(v.id, run.run_id);
  assert.equal(v.meanBefore, run.q1.mean_ms_before);
  assert.equal(v.payloads, run.privacy.payloads);
  assert.equal(v.llmPayloads, run.privacy.llm_payloads);
  assert.equal(v.speedupPct, run.twin.speedup_pct);
  assert.equal(v.indexCols, "(c_bbbbbbbb, c_cccccccc)");
  assert.deepEqual(v.actions, ["add index on t_aaaaaaaa (c_bbbbbbbb, c_cccccccc)"]);
  assert.equal(v.migration, "-- m");
  assert.equal(v.templateSql, "SELECT ?");
  assert.equal(v.templateSqlReal, null);
  assert.equal(v.answer, null);
  assert.equal(v.src.twin, `${run.run_id}, median of ${run.twin.runs} runs on the twin`);
});

test("tool_calls as the ai service's list", () => {
  const v = viewOf({ ...bundle, llm: { ...bundle.llm, tool_calls: [{ tool_call_id: "tc_1", name: "get_plan" }, { tool_call_id: "tc_2", name: "simulate" }] } }, fb);
  assert.equal(v.llm.toolCalls, 2);
});

test("action wording for a partition and an unknown type", () => {
  assert.equal(actionWords(bundle, { type: "partition", table: "t_22222222", column: "c_66666666", scheme: "monthly" }), "partition big_table by d (monthly)");
  assert.equal(actionWords(bundle, { type: "other" }), "other");
});
