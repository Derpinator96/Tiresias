// Run: npm test. Stage mapping of live progress events (src/lib/progress.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { reached, replayFrames, stageOf, toolOf } from "../src/lib/progress.ts";

test("stage follows the latest tool call, then llm, then dba", () => {
  assert.equal(stageOf([], false, false), "source");
  const ev = ["tool get_slow_templates -> tc_1", "LLM service unavailable (HTTP 503), retrying", "tool run_rl -> tc_2"];
  assert.equal(stageOf(ev, false, false), "rl");
  assert.equal(stageOf(ev.slice(0, 2), false, false), "gateway");
  assert.equal(stageOf(ev, true, false), "llm");
  assert.equal(stageOf(ev, true, true), "dba");
  assert.equal(toolOf("nim failed (MissingKey), asking gemini instead"), null);
});

test("reached collects every stage touched, all of them when done", () => {
  const r = reached(["tool mine_candidates -> tc_1", "tool simulate -> tc_2"], false, false);
  assert.deepEqual([...r].sort(), ["gateway", "miner", "source", "twin"]);
  assert.equal(reached([], true, true).size, 8);
});

test("replay frames step through every event and end where a finished live run ends", () => {
  const ev = ["tool get_slow_templates -> tc_1", "tool mine_candidates -> tc_2", "tool run_rl -> tc_3"];
  const f = replayFrames(ev);
  assert.equal(f.length, ev.length + 3);
  assert.deepEqual(f.map((x) => x.events.length), [0, 1, 2, 3, 3, 3]);
  const last = f.at(-1);
  assert.deepEqual([...reached(last.events, last.answered, last.done)], [...reached(ev, true, true)]);
  assert.equal(stageOf(f[3].events, false, false), "rl");
});
