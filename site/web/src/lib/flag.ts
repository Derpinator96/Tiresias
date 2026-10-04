// Splits a blocked draft into plain and flagged parts: each number the checker rejected is
// flagged wherever it stands as a whole number token. Pure, no imports (tests/flag.test.mjs).

export type Part = { text: string; flagged: boolean };

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function flagNumbers(text: string, unmatched: string[]): Part[] {
  const nums = [...new Set(unmatched)].filter(Boolean).sort((a, b) => b.length - a.length);
  if (!nums.length) return [{ text, flagged: false }];
  const re = new RegExp(`(?<![\\d.])(?:${nums.map(esc).join("|")})(?![\\d]|\\.\\d)`, "g");
  const out: Part[] = [];
  let at = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > at) out.push({ text: text.slice(at, m.index), flagged: false });
    out.push({ text: m[0], flagged: true });
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at), flagged: false });
  return out;
}
