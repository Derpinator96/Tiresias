// Run: npm test (node --test, Node 24 strips the types from logic.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { speedupPct, bellman, tar } from "../src/lib/logic.ts";
import run from "../src/data/run_d1b30d38.json" with { type: "json" };

test("speedup recomputed from the twin times matches the run record", () => {
  assert.equal(speedupPct(run.twin.before_ms, run.twin.after_ms).toFixed(1), run.twin.speedup_pct.toFixed(1));
});

test("bellman matches rl/search.py's update", () => {
  // q_init 1.0, alpha 0.1, gamma 0.9 (config.yaml), reward 0.5, best next 1.0
  assert.ok(Math.abs(bellman(1, 0.5, 1, 0.1, 0.9) - 1.04) < 1e-12);
  // STOP: target 0, so Q moves 10% toward 0
  assert.ok(Math.abs(bellman(1, 0, 0, 0.1, 0.9) - 0.9) < 1e-12);
});

test("tar archive extracts with the system tar", () => {
  const dir = mkdtempSync(join(tmpdir(), "bt-tar-"));
  const files = { "migration.sql": "CREATE INDEX x;\n", "rollback.sql": "DROP INDEX x;\n".repeat(100) };
  writeFileSync(join(dir, "p.tar"), tar(files));
  for (const [name, text] of Object.entries(files)) {
    assert.equal(execFileSync("tar", ["-xOf", join(dir, "p.tar"), name], { encoding: "utf8" }), text);
  }
});
