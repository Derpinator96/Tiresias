// Run: npm test. Flagging rejected numbers in a blocked draft (src/lib/flag.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { flagNumbers } from "../src/lib/flag.ts";

const flagged = (parts) => parts.filter((p) => p.flagged).map((p) => p.text);

test("flags whole number tokens only", () => {
  const p = flagNumbers("From 681.2 ms to 272.5 ms, 690 calls, 69 MB, 69.5 s, v1.69.", ["69", "681.2"]);
  assert.deepEqual(flagged(p), ["681.2", "69"]);
  assert.equal(p.map((x) => x.text).join(""), "From 681.2 ms to 272.5 ms, 690 calls, 69 MB, 69.5 s, v1.69.");
});

test("a number at the end of a sentence still counts", () => {
  assert.deepEqual(flagged(flagNumbers("Saved 356.286.", ["356.286"])), ["356.286"]);
});

test("nothing to flag returns the text as one part", () => {
  assert.deepEqual(flagNumbers("plain", []), [{ text: "plain", flagged: false }]);
});
