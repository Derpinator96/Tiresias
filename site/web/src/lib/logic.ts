// Pure functions the playground computes in the browser. No imports, so tests/logic.test.mjs
// can load this file with Node's built-in type stripping.

/** Percent faster, as the twin reports it: (1 - after / before) x 100. */
export function speedupPct(beforeMs: number, afterMs: number): number {
  return (1 - afterMs / beforeMs) * 100;
}

/** One tabular Q-learning update, the same line as rl/search.py:
 *  Q(s,a) + alpha * (R + gamma * max Q(s',a') - Q(s,a)). */
export function bellman(q: number, reward: number, maxNext: number, alpha: number, gamma: number): number {
  return q + alpha * (reward + gamma * maxNext - q);
}

/** A ustar archive of text files, readable by `tar -xf`. */
export function tar(files: Record<string, string>, mtimeS = 0): Uint8Array {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  for (const [name, text] of Object.entries(files)) {
    const body = enc.encode(text);
    const h = new Uint8Array(512);
    const put = (s: string, off: number) => h.set(enc.encode(s), off);
    const oct = (n: number, width: number) => n.toString(8).padStart(width - 1, "0") + "\0";
    put(name, 0);
    put(oct(0o644, 8), 100);
    put(oct(0, 8), 108);
    put(oct(0, 8), 116);
    put(oct(body.length, 12), 124);
    put(oct(mtimeS, 12), 136);
    put("        ", 148); // checksum is computed with its own field as spaces
    put("0", 156);
    put("ustar\u000000", 257);
    put(h.reduce((a, b) => a + b, 0).toString(8).padStart(6, "0") + "\0 ", 148);
    parts.push(h, body, new Uint8Array((512 - (body.length % 512)) % 512));
  }
  parts.push(new Uint8Array(1024));
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}
