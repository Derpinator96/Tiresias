// Run: npm test. Slow-query alert email (src/lib/alerts-shared.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { alertEmail, alertLines } from "../src/lib/alerts-shared.ts";

const A = {
  id: "al_0000beef", created_at: "2026-10-04T12:00:00Z", to: "dba@example.com",
  template_id: "q_5ce3d2f7", sql: "SELECT p.category FROM sales s WHERE s.x < $1 -- CANARY_QXZ7732_VK", example: null,
  calls: 405, mean_ms: 664.5, total_ms: 269122, threshold_ms: 100,
  fixes: ["add an index on sales (region_id, transaction_date)"], migration: 'CREATE INDEX CONCURRENTLY "bt_i" ON "sales" ("region_id");',
  rollback: 'DROP INDEX CONCURRENTLY IF EXISTS "bt_i";', twin: { before_ms: 681.2, after_ms: 272.5 }, twin_mode: "recorded",
  emailed: false, email_error: null,
};

test("the email names the query, its stats, the fix, the SQL and the link", () => {
  const m = alertEmail(A, "http://localhost:5173/alerts?id=al_0000beef");
  assert.match(m.subject, /^Slow query on pg-prod: 664\.5 ms average, SELECT p\.category/);
  for (const part of ["664.5 ms on average over 405 calls", "add an index on sales", "681.2 ms to 272.5 ms, 60% faster (recorded mode", 'CREATE INDEX CONCURRENTLY "bt_i"', "DROP INDEX", "http://localhost:5173/alerts?id=al_0000beef"]) {
    assert.ok(m.text.includes(part), part);
  }
  assert.ok(!m.text.includes("CANARY") && !m.html.includes("CANARY"));
  assert.ok(m.html.includes("s.x &lt; $1") && m.html.includes('href="http://localhost:5173/alerts?id=al_0000beef"'));
});

test("no twin row and no fix still give a stats line", () => {
  assert.equal(alertLines({ ...A, twin: null, fixes: [] }).length, 1);
});
