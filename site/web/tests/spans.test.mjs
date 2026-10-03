import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { q1Spans, niceTicks, end } from "../src/lib/spans.ts";
import run from "../src/data/run_d1b30d38.json" with { type: "json" };

// The waterfall takes a run view; this is the view the run record produces (src/lib/run-view.ts).
const view = (r) => ({ meanBefore: r.q1.mean_ms_before, twinBefore: r.twin.before_ms, twinAfter: r.twin.after_ms, runs: r.twin.runs, storageMb: r.twin.storage_mb, predictedBefore: r.search.predicted_before_ms, predictedAfter: r.search.predicted_after_ms, estimatorLabel: r.search.estimator_label });

test("spans come from the run record and sit end to end", () => {
  const s = q1Spans(view(run));
  assert.equal(s[0].dur, run.q1.mean_ms_before);
  assert.equal(s[2].dur, run.twin.after_ms);
  for (let i = 1; i < s.length; i++) assert.equal(s[i].start, s[i - 1].start + s[i - 1].dur);
  assert.equal(end(s), s.reduce((a, x) => a + x.dur, 0));
});

test("changing the record changes the spans", () => {
  const s = q1Spans({ ...view(run), twinAfter: 10 });
  assert.equal(s[2].dur, 10);
});

test("a missing figure leaves its span out", () => {
  const s = q1Spans({ ...view(run), meanBefore: null });
  assert.equal(s.length, 4);
  assert.equal(s[0].id, "twin-before");
  assert.equal(s[0].start, 0);
});

test("niceTicks", () => {
  assert.deepEqual(niceTicks(100, 5), [0, 20, 40, 60, 80, 100]);
  assert.ok(niceTicks(912.9).at(-1) <= 912.9);
});

test("chart components hold no literal numbers: every figure comes from data", () => {
  for (const f of ["src/components/viz/stage-visuals.tsx", "src/components/viz/home-results.tsx", "src/app/(site)/page.tsx"]) {
    const code = readFileSync(new URL(`../${f}`, import.meta.url), "utf8").replace(/\/\/.*$/gm, "").replace(/className="[^"]*"/g, "");
    const bad = code.match(/(?<![\w.#-])\d+\.\d+|(?<![\w.#"'-])\d{2,}(?![\w%])/g) ?? [];
    assert.deepEqual(bad, [], `${f}: ${bad.join(", ")}`);
  }
});
