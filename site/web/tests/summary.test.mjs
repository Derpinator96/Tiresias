// Run: npm test. The plain-words summary (src/lib/summary.ts) and matchAsked (src/lib/ask-shared.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { fixesOf, plainSummary, sqlOf } from "../src/lib/summary.ts";
import { matchAsked } from "../src/lib/ask-shared.ts";

const MIGRATION = 'CREATE INDEX CONCURRENTLY "bt_x" ON "sales" ("region_id", "transaction_date");\n-- rewritten query (application code change)\nSELECT 1';

test("fixes come from the migration SQL", () => {
  assert.deepEqual(fixesOf(MIGRATION), ["add an index on sales (region_id, transaction_date)", "rewrite the query in the application (a code change)"]);
  assert.equal(sqlOf('query "SELECT 1"'), "SELECT 1");
});

test("a fast matched query is called not slow; the outcome uses the job's numbers", () => {
  const s = plainSummary({
    question_id: "qn_1", template_ids: [], done: true, twin_mode: "recorded", threshold_ms: 100, migration: MIGRATION,
    matched: [{ template_id: "q_a", sql: "SELECT COUNT(*) FROM products", mean_ms: 3.2, slow: false },
              { template_id: "q_b", sql: "SELECT SUM(amount) FROM sales", mean_ms: 681.2, slow: true }],
    results: [{ template_id: "q_b", label: 'query "SELECT SUM(amount) FROM sales"', before_ms: 681.2, after_ms: 272.5, saved_ms: 408.7, pct: 60 }],
    sim: { runs: 5, storage_mb_delta: 69, write_ms_delta: 0.1 },
  });
  assert.match(s.asked[0], /products is not slow: 3\.2 ms on average, under the 100 ms threshold/);
  assert.match(s.outcome.join(" "), /681\.2 ms before.*index on sales.*272\.5 ms, 60% faster \(recorded mode.*69 MB more on disk and \+0\.1 ms per insert/);
});

test("matchAsked keeps only the question's templates and never throws", async () => {
  const job = { question_id: "qn_1", template_ids: ["q_a"], done: false };
  await matchAsked(job, async () => ({ status: 200, body: { threshold_ms: 100, templates: [
    { template_id: "q_a", sql: "SELECT 1", mean_ms: 3.2, slow: false }, { template_id: "q_b", sql: "SELECT 2", mean_ms: 500, slow: true }] } }));
  assert.deepEqual(job.matched, [{ template_id: "q_a", sql: "SELECT 1", mean_ms: 3.2, slow: false }]);
  const bad = { question_id: "qn_2", template_ids: ["q_a"], done: false };
  await matchAsked(bad, async () => { throw new Error("down"); });
  assert.equal(bad.matched, null);
});

const CAT = { template_id: "q_c", sql: "SELECT p.category, SUM(s.amount) FROM sales s JOIN products p ON p.product_id = s.product_id", mean_ms: 681.2, slow: true };
const LOOKUP = { template_id: "q_p", sql: "SELECT COUNT(*) FROM products WHERE category = $1 -- CANARY_X", mean_ms: 3.2, slow: false };
const base = { question_id: "qn_1", template_ids: [], done: true, threshold_ms: 100, migration: MIGRATION, results: [] };

test("verdict: the slow part is in another table", () => {
  const s = plainSummary({ ...base, matched: [CAT, LOOKUP] }, "why is the products report slow");
  assert.equal(s.verdict, "Not products itself. Queries on it alone are fast (3.2 ms). The slow query joins products but spends its time reading sales (681.2 ms on average), so the fix goes on sales.");
  assert.ok(!s.asked.join(" ").includes("CANARY"));
});

test("verdict: nothing asked about is slow, and no fix is offered", () => {
  const s = plainSummary({ ...base, matched: [LOOKUP] }, "why is the products lookup slow");
  assert.match(s.verdict, /^No: nothing you asked about is slow/);
  assert.deepEqual(s.outcome, []);
});

test("verdict: the asked table is the slow one", () => {
  const s = plainSummary({ ...base, matched: [CAT] }, "why is the sales report slow");
  assert.match(s.verdict, /^Yes: one query you asked about is slow \(681\.2 ms on average\)/);
});
