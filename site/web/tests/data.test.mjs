// Run: npm test. Data questions with fake services (src/lib/data-shared.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { runData } from "../src/lib/data-shared.ts";

const TABLES = [{ table: "products", code: "t_1", rows: 100, columns: [{ name: "name", type: "text", code: "c_1" }], sample: [] }];

function fakes({ sql = { status: 200, body: { explanation: "Top seller.", sql: "SELECT name FROM products", seconds: 2.5, llm: { provider: "nim", model: "m" } } },
                 query = { status: 200, body: { sql: "SELECT name FROM products", columns: ["name"], rows: [["Tea"]], truncated: false, ms: 12.5 } } } = {}) {
  const seen = [];
  const gateway = async (path, body) => { seen.push(["gateway", path, body]);
    return path.startsWith("/v1/private/tables") ? { status: 200, body: TABLES } : query; };
  const ai = async (path, body) => { seen.push(["ai", path, body]); return sql; };
  return { gateway, ai, seen };
}

test("schema goes to the LLM as names and types only; rows come back from the gateway", async () => {
  const f = fakes();
  const r = await runData("which product sold most?", f.gateway, f.ai);
  assert.equal(r.rows[0][0], "Tea");
  assert.equal(r.explanation, "Top seller.");
  const toAi = f.seen.find((x) => x[0] === "ai")[2];
  assert.deepEqual(toAi.schema, [{ table: "products", columns: [{ name: "name", type: "text" }] }]);
  assert.ok(!JSON.stringify(toAi).includes("sample") && !JSON.stringify(toAi).includes("t_1"));
});

test("each failing step is named", async () => {
  let r = await runData("q", fakes().gateway, fakes({ sql: { status: 503, body: { detail: { error: "RateLimited" } } } }).ai);
  assert.deepEqual(r, { error: "RateLimited", step: "llm" });
  r = await runData("q", fakes().gateway, fakes({ sql: { status: 200, body: { explanation: "No.", sql: "" } } }).ai);
  assert.equal(r.step, "llm");
  const f = fakes({ query: { status: 400, body: { detail: "only SELECT is allowed" } } });
  r = await runData("q", f.gateway, f.ai);
  assert.equal(r.step, "query");
  assert.match(r.error, /only SELECT/);
});
