// Run: npm test. The live Ask job (src/lib/ask-shared.ts) with fake gateway and ai services,
// mirroring dashboard/tests/test_home.py with neutral names.
import { test } from "node:test";
import assert from "node:assert/strict";
import { runJob, sqlStatements } from "../src/lib/ask-shared.ts";

const MIGRATION = [
  "-- Blind Tuner migration for cfg_00000001 (search: q_learning).",
  "-- 1. add_index on shop (city, day)",
  'CREATE INDEX CONCURRENTLY "bt_shop_city_day" ON "shop" ("city", "day");',
  "",
].join("\n");
const CONFIG = { config_id: "cfg_00000001", search: "q_learning", actions: [{ type: "add_index", table: "t_00000001", columns: ["c_00000001"] }] };
const SIM = { config_id: "cfg_00000001", source: "twin", templates: [{ template_id: "q_00000001", before_ms: 200, after_ms: 50 }], runs: 5, write_ms_delta: 0.03, storage_mb_delta: 68 };

function fakes({ askStatus = 200, checker = "ok", config = CONFIG, simulation = SIM } = {}) {
  const calls = [];
  const gateway = async (path, body) => {
    calls.push(path);
    if (path === "/v1/answers/dehash") return { status: 200, body: { text: body.text.replaceAll("t_00000001", "shop").replaceAll("q_00000001", 'query "SELECT ..."') } };
    if (path === "/v1/simulate/twin") return { status: 200, body: SIM };
    if (path === "/v1/approve") return { status: 200, body: { files: { "migration.sql": MIGRATION, "rollback.sql": 'DROP INDEX CONCURRENTLY IF EXISTS "bt_shop_city_day";' } } };
    if (path === "/v1/meta/tables") return { status: 200, body: [{ table: "t_00000001", rows: 1000 }] };
    throw new Error(`unexpected ${path}`);
  };
  const ai = async (path) => {
    calls.push(path);
    if (path === "/ai/ask") {
      return askStatus === 200
        ? { status: 200, body: { status: checker, unmatched: checker === "ok" ? [] : ["85"], answer: { text: "Index t_00000001.", numbers: [] }, tool_calls: 5, config, simulation } }
        : { status: askStatus, body: { detail: { error: "rate limited", detail: "quota" } } };
    }
    if (path === "/ai/rl/run") return { status: 200, body: { config: CONFIG } };
    throw new Error(`unexpected ${path}`);
  };
  return { gateway, ai, calls };
}

const job = () => ({ question_id: "qn_00000001", template_ids: ["q_00000001"], done: false });

test("sqlStatements drops comments and keeps rewritten queries", () => {
  assert.equal(sqlStatements(MIGRATION), 'CREATE INDEX CONCURRENTLY "bt_shop_city_day" ON "shop" ("city", "day");');
  const rewrite = "-- 2. rewrite r1 of template q_1: a suggested application code change, not run by this file.\n"
    + "--    Original (latest logged query):\n--      SELECT 1\n--    Rewritten:\n--      SELECT 2\n--      FROM t\n";
  assert.equal(sqlStatements(rewrite), "-- rewritten query (application code change)\nSELECT 2\nFROM t");
});

test("answer dehashed, the agent's own measurement reused, SQL and time saved", async () => {
  const f = fakes();
  const j = job();
  await runJob(j, f.gateway, f.ai);
  assert.equal(j.done, true);
  assert.equal(j.error, undefined);
  assert.equal(j.ask.hashed, "Index t_00000001.");
  assert.equal(j.ask.real, "Index shop.");
  assert.ok(!f.calls.includes("/v1/simulate/twin") && !f.calls.includes("/ai/rl/run"));
  assert.equal(j.results[0].saved_ms, 150);
  assert.equal(j.results[0].pct, 75);
  assert.equal(j.results[0].label, 'query "SELECT ..."');
  assert.equal(j.rows, 1000);
  assert.ok(j.migration.startsWith("CREATE INDEX CONCURRENTLY"));
});

test("an LLM error still gives a search, a twin measurement and SQL", async () => {
  const f = fakes({ askStatus: 503 });
  const j = job();
  await runJob(j, f.gateway, f.ai);
  assert.equal(j.ask.detail, "quota");
  assert.ok(f.calls.includes("/ai/rl/run") && f.calls.includes("/v1/simulate/twin"));
  assert.ok(j.migration);
});

test("a blocked answer is not dehashed", async () => {
  const f = fakes({ checker: "blocked_by_checker" });
  const j = job();
  await runJob(j, f.gateway, f.ai);
  assert.equal(j.ask.real, undefined);
  assert.deepEqual(j.ask.unmatched, ["85"]);
});

test("a failed step is reported, never left waiting", async () => {
  const f = fakes({ askStatus: 503 });
  const ai = async (path, body) => (path === "/ai/rl/run" ? { status: 500, body: {} } : f.ai(path, body));
  const j = job();
  await runJob(j, f.gateway, ai);
  assert.equal(j.done, true);
  assert.match(j.error, /the search failed \(HTTP 500/);
});
