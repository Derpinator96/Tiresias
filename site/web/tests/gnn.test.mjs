import { test } from "node:test";
import assert from "node:assert/strict";
import { numericFeatures, shares, reach, layout, serves, misestimate, opIndex, ownCost } from "../src/lib/gnn.ts";
import plans from "../src/data/gnn_plans.json" with { type: "json" };
import spec from "../src/data/gnn_spec.json" with { type: "json" };
import m from "../src/data/measurements.json" with { type: "json" };

const q1 = plans.plans[0].nodes;
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);

test("features equal models/gnn/features.py on the doc's plan (python3 reference values)", () => {
  const f = numericFeatures(q1);
  [0.6931471805599453, 14.038654909278163, 9.210440366976517, 3.4965075614664802, 0, 0, 0].forEach((v, i) => close(f[0][i], v));
  [9.798182590890704, 14.030622744032508, 14.030622744032508, 2.1972245773362196, 0, 2, 0].forEach((v, i) => close(f[1][i], v));
  assert.equal(spec.ops.length, 42);
  assert.equal(opIndex(spec.ops, "Seq Scan"), spec.ops.indexOf("Seq Scan"));
});

test("shares sum to 1 and point at the scan", () => {
  for (const by of ["cost", "time"]) {
    const s = shares(q1, by);
    close(s.reduce((a, b) => a + b, 0), 1);
    assert.ok(s[1] > 0.99, by);
  }
  assert.deepEqual(ownCost(q1), [10000, 1240000]);
});

test("receptive field grows one level per layer, up the tree", () => {
  const n = plans.plans[1].nodes;
  assert.deepEqual([...reach(n, 0, 0)], [0]);
  assert.deepEqual([...reach(n, 0, 1)].sort(), [0, 1]);
  assert.deepEqual([...reach(n, 0, 2)].sort(), [0, 1, 2, 3]);
  assert.equal(reach(n, 0, spec.layers).size, n.length);
  assert.deepEqual([...reach(n, 4, 3)], [4]);
});

test("layout: depth as y, leaf units as x, parents centred, no sibling overlap at any depth", () => {
  const n = plans.plans[1].nodes, p = layout(n), at = (id) => p.find((x) => x.id === id);
  close(at(1).x, (at(2).x + at(3).x) / 2);
  assert.ok(at(0).y < at(1).y && at(1).y < at(3).y && at(3).y < at(4).y);
  // 3 levels: the root has 2 children, one with 2 and one with 3 children.
  const t = [[0, null], [1, 0], [2, 0], [3, 1], [4, 1], [5, 2], [6, 2], [7, 2]].map(([node_id, parent_id]) => ({ node_id, parent_id, op: "x", est_rows: 1, est_cost: 1, width: 1 }));
  const q = layout(t), qa = (id) => q.find((x) => x.id === id);
  assert.deepEqual([3, 4, 5, 6, 7].map((id) => qa(id).x), [0, 1, 2, 3, 4]);
  close(qa(1).x, 0.5); close(qa(2).x, 3); close(qa(0).x, 1.75);
  assert.deepEqual([0, 1, 2, 3].map((id) => qa(id).y), [0, 1, 1, 2]);
  for (const a of q) for (const b of q) if (a.id !== b.id && a.y === b.y) assert.ok(Math.abs(a.x - b.x) >= 1, `${a.id} and ${b.id} overlap`);
});

test("serving rule on the dated scores: the reference GNN would beat the baseline", () => {
  const [g, , pg] = m.gnn.models;
  assert.equal(serves(g.median, pg.median), "gnn");
  assert.equal(serves(3.3, 3.266), "baseline");
  assert.equal(misestimate(1, 4), 4);
  assert.ok(misestimate(18000, 20000) < spec.misestimate_ratio_alert);
});

import { planOptions, predictedShares, shortSql } from "../src/lib/gnn.ts";

test("bundle plan options: asked templates first, only those with a plan, labelled by real SQL", () => {
  const b = {
    template_ids: ["q_bbbbbbbb"],
    plans: { q_aaaaaaaa: [{ nodes: q1 }], q_bbbbbbbb: [{ nodes: q1 }], q_cccccccc: [] },
    names: { q_aaaaaaaa: "SELECT   1\n FROM x", q_bbbbbbbb: "SELECT " + "y".repeat(80) },
  };
  const o = planOptions(b);
  assert.deepEqual(o.map((x) => x.tid), ["q_bbbbbbbb", "q_aaaaaaaa"]);
  assert.equal(o[1].label, "SELECT 1 FROM x");
  assert.equal(o[0].label.length, 60);
  assert.ok(o[0].label.endsWith("..."));
  assert.equal(shortSql("abc", 3), "abc");
});

test("predicted shares follow node order and default to 0", () => {
  const p = { nodes: [{ node_id: 1, share: 0.99 }, { node_id: 0, share: 0.01 }] };
  assert.deepEqual(predictedShares(q1, p), [0.01, 0.99]);
  assert.deepEqual(predictedShares(q1, null), [0, 0]);
});
