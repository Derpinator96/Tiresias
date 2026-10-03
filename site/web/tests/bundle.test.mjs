// Run: npm test. buildBundle (src/lib/bundle-build.ts) with fake gateway and ai services, and the
// history summary (src/lib/bundle.ts). Neutral names only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildBundle } from "../src/lib/bundle-build.ts";
import { summarize } from "../src/lib/bundle.ts";

const PLAN = { plan_id: "p1", template_id: "q_00000001", setup_id: "s", source: "logged", nodes: [{ node_id: 0, parent_id: null, op: "Seq Scan", est_rows: 1, est_cost: 1, width: 8, relation: "t_00000001" }] };
const CONFIG = { config_id: "cfg_00000001", search: "q_learning", actions: [{ type: "add_index", table: "t_00000001", columns: ["c_00000001"] }] };
const LEDGER = { outbound_payloads: 7, outbound_canary_hits: 0, outbound_blocked: 0, canaries_planted: 12, entries: [] };
const BEFORE = { outbound_payloads: 3, outbound_canary_hits: 0, outbound_blocked: 0, canaries_planted: 12 };

const job = () => ({
  question_id: "qn_00000001", template_ids: ["q_00000001"], done: true,
  ask: { status: 200, checker: "ok", hashed: "Index t_00000001.", real: "Index shop." },
  ask_body: { status: "ok", events: ["tool get_slow_templates", "tool run_rl"], llm: { provider: "gemini", model: "m" }, seconds: 12.5, tool_calls: 2, failovers: [] },
  config: CONFIG, simulation: { config_id: "cfg_00000001", source: "twin", templates: [{ template_id: "q_00000001", before_ms: 200, after_ms: 50 }], runs: 5, write_ms_delta: 0.03, storage_mb_delta: 68 },
  results: [{ template_id: "q_00000001", label: "q", before_ms: 200, after_ms: 50, saved_ms: 150, pct: 75 }],
  rl: { config: CONFIG, label: "search", steps: 3 },
});

function fakes({ names = true, fail = [] } = {}) {
  const calls = [];
  const reply = (path, body) => {
    if (fail.includes(path)) return { status: 500, body: { detail: "boom" } };
    switch (path) {
      case "/v1/private/names": return names ? { status: 200, body: { t_00000001: "shop", c_00000001: "shop.city", q_00000001: "SELECT 1\nFROM shop" } } : { status: 404, body: {} };
      case "/v1/answers/dehash": return { status: 200, body: { text: body.text.split("\n").map((c) => ({ t_00000001: "shop", c_00000001: "shop.city", q_00000001: 'query "SELECT 1"' })[c] ?? c).join("\n") } };
      case "/v1/templates/slow": return { status: 200, body: [{ template_id: "q_00000001", sql: "SELECT ...", calls: 3, mean_ms: 200, total_ms: 600, columns: [] }] };
      case "/v1/templates/q_00000001/plans": return { status: 200, body: [PLAN] };
      case "/v1/ledger": return { status: 200, body: LEDGER };
      case "/v1/meta/tables": return { status: 200, body: [{ table: "t_00000001", rows: 1000, size_mb: 10, writes_per_s: 1 }] };
      case "/v1/simulate/hypopg": return { status: 200, body: { plans: [PLAN], index_storage_mb: 68 } };
      case "/ai/gnn/estimator": return { status: 200, body: { estimator: "postgres_calibrated", label: "estimator: Postgres cost x calibration (GNN pending)" } };
      case "/ai/gnn/predict": return { status: 200, body: body.map((p) => ({ plan_id: p.plan_id, estimator: "postgres_calibrated", total_ms: 180, nodes: [] })) };
      case "/ai/gnn/explain": return { status: 200, body: { estimator: "postgres_calibrated", label: "l", predicted_total_ms: 180, top_nodes: [], misestimate_alert_ratio: 100, misestimates: [] } };
      case "/ai/mine": return { status: 200, body: { candidates: [{ cand_id: "cand_1", table: "t_00000001", columns: ["c_00000001"], support: 0.5, evidence: { items: [], templates: [] } }] } };
      default: throw new Error(`unexpected ${path}`);
    }
  };
  const call = async (path, body) => { calls.push(path); return reply(path, body); };
  return { gateway: call, ai: call, calls };
}

test("every call succeeds: all fields filled", async () => {
  const f = fakes();
  const b = await buildBundle(job(), "why slow?", f.gateway, f.ai, BEFORE);
  assert.equal(b.id, "qn_00000001");
  assert.equal(b.question, "why slow?");
  assert.ok(!Number.isNaN(Date.parse(b.created_at)));
  assert.deepEqual(b.events, ["tool get_slow_templates", "tool run_rl"]);
  assert.deepEqual(b.llm, { provider: "gemini", model: "m", seconds: 12.5, tool_calls: 2, failovers: [] });
  assert.equal(b.estimator.estimator, "postgres_calibrated");
  assert.equal(b.slow.length, 1);
  assert.equal(b.plans.q_00000001[0].plan_id, "p1");
  assert.equal(b.predictions.q_00000001.total_ms, 180);
  assert.equal(b.explain.q_00000001.predicted_total_ms, 180);
  assert.equal(b.mine.candidates[0].cand_id, "cand_1");
  assert.equal(b.rl.steps, 3);
  assert.equal(b.config.config_id, "cfg_00000001");
  assert.equal(b.sim.runs, 5);
  assert.equal(b.hypopg.index_storage_mb, 68);
  assert.deepEqual(b.ledger, { before: BEFORE, after: { outbound_payloads: 7, outbound_canary_hits: 0, outbound_blocked: 0, canaries_planted: 12 } });
  assert.equal(b.tables[0].rows, 1000);
  assert.equal(b.names.q_00000001, "SELECT 1\nFROM shop");
  assert.ok(!f.calls.includes("/v1/answers/dehash"));
});

test("names endpoint 404: codes across the bundle are dehashed once", async () => {
  const f = fakes({ names: false });
  const b = await buildBundle(job(), "q", f.gateway, f.ai, BEFORE);
  assert.equal(f.calls.filter((p) => p === "/v1/answers/dehash").length, 1);
  assert.deepEqual(b.names, { q_00000001: "SELECT 1", t_00000001: "shop", c_00000001: "shop.city" });
});

test("a failing enrichment call leaves its field null, never throws", async () => {
  const f = fakes({ fail: ["/ai/mine", "/ai/gnn/predict", "/v1/ledger", "/v1/templates/q_00000001/plans"] });
  const b = await buildBundle(job(), "q", f.gateway, f.ai, BEFORE);
  assert.equal(b.mine, null);
  assert.deepEqual(b.plans, { q_00000001: [] });
  assert.equal(b.predictions.q_00000001, null);
  assert.deepEqual(b.ledger.after, { outbound_payloads: 0, outbound_canary_hits: 0, outbound_blocked: 0, canaries_planted: 0 });
  assert.equal(b.slow.length, 1);
});

test("a job without a config skips hypopg; a thrown call is a null field", async () => {
  const f = fakes();
  const ai = async (path, body) => { if (path === "/ai/gnn/estimator") throw new Error("down"); return f.ai(path, body); };
  const j = { ...job(), config: null, rl: undefined, simulation: undefined, error: "the search failed" };
  const b = await buildBundle(j, "q", f.gateway, ai, BEFORE);
  assert.equal(b.estimator, null);
  assert.equal(b.hypopg, null);
  assert.equal(b.rl, null);
  assert.equal(b.sim, null);
  assert.ok(!f.calls.includes("/v1/simulate/hypopg"));
});

test("summarize: one line per bundle", async () => {
  const f = fakes();
  const b = await buildBundle(job(), "why slow?", f.gateway, f.ai, BEFORE);
  assert.deepEqual(summarize(b), { id: "qn_00000001", question: "why slow?", created_at: b.created_at, template_ids: ["q_00000001"], ok: true, speedup_pct: 75, error: null });
  const failed = await buildBundle({ ...job(), error: "twin 409" }, "q", f.gateway, f.ai, BEFORE);
  assert.equal(summarize(failed).ok, false);
  assert.equal(summarize(failed).error, "twin 409");
});
