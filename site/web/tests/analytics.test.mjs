// Run: npm test. Query analytics (src/lib/analytics-shared.ts) and roles (src/lib/auth-shared.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { isSpike, summarize } from "../src/lib/analytics-shared.ts";
import { CAN, signupProblem } from "../src/lib/auth-shared.ts";

const ev = (t, ms, user = "a@x.io", ok = true) => ({ t, user, role: "analyst", label: "q", kind: "slow", sql: "SELECT 1", ms, rows: 1, ok, error: ok ? null : "boom" });

test("a spike is a successful run at or over the threshold", () => {
  assert.ok(isSpike(ev(0, 100), 100));
  assert.ok(!isSpike(ev(0, 99.9), 100));
  assert.ok(!isSpike(ev(0, 500, "a@x.io", false), 100));
});

test("summary counts spikes, the last minute, percentiles and users", () => {
  const now = 200_000;
  const s = summarize([ev(10_000, 20), ev(150_000, 664.5, "b@x.io"), ev(170_000, 15), ev(190_000, 185.7, "b@x.io"), ev(195_000, 0, "a@x.io", false)], 100, now);
  assert.equal(s.runs, 5);
  assert.equal(s.perMinute, 4);
  assert.equal(s.spikes, 2);
  assert.equal(s.p50, 20);
  assert.equal(s.p95, 664.5);
  assert.equal(s.slowest.ms, 664.5);
  assert.deepEqual(s.byUser, [{ user: "a@x.io", runs: 3, spikes: 0 }, { user: "b@x.io", runs: 2, spikes: 2 }]);
});

test("RBAC: analysts use the workbench only; an unknown role cannot sign up", () => {
  assert.ok(CAN.workbench.includes("analyst") && !CAN.analytics.includes("analyst") && !CAN.alerts.includes("analyst"));
  assert.match(signupProblem("a@x.io", "A", "longenough", "admin"), /role/);
  assert.equal(signupProblem("a@x.io", "A", "longenough", "analyst"), null);
});
