// One frame of the hashing glitch: plain SQL scrambles and settles left to right into the hashed
// SQL. Pure and import-free so tests/hashing.test.mjs can load it with Node's type stripping.

const CHARSET = "0123456789abcdef_?";
const WINDOW = 12; // scrambled characters ahead of the settle front

/** t runs 0..1. Before the front: `to`; the next WINDOW characters: random; the rest: `from`.
 *  The length moves linearly from from.length to to.length. */
export function glitchFrame(from: string, to: string, t: number, rand: () => number): string {
  if (t <= 0) return from;
  if (t >= 1) return to;
  const len = Math.round(from.length + (to.length - from.length) * t);
  const front = Math.floor(t * (len + WINDOW)) - WINDOW;
  let out = "";
  for (let i = 0; i < len; i++) {
    if (i < front) out += to[i] ?? " ";
    else if (i < front + WINDOW) out += /\s/.test(to[i] ?? from[i] ?? "") ? (to[i] ?? from[i]) : CHARSET[Math.floor(rand() * CHARSET.length)];
    else out += from[i] ?? " ";
  }
  return out;
}
