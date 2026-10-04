// Browser version of what the gateway does to one query (gateway/hashing.py, gateway/strip.py).
// No imports, so tests/hashing.test.mjs can load it with Node's type stripping.
//
// Same as the gateway: code = prefix + "_" + first 8 hex of HMAC-SHA256(key, text); tables hash
// "table", columns hash "table.column"; values, parameters and comments become ?; aliases and
// qualifiers are dropped; roles EQ, JOIN, RANGE, GROUP, ORDER, SELECT; fail closed when unsure.
// SIMPLIFIED: a tokenizer, not sqlglot's parse tree, and no schema, so an unqualified column with
// two tables in scope always fails closed (the gateway asks its catalog which table owns it).

export const HEX_CHARS = 8; // config.yaml hashing.hmac_code_hex_chars

export function newKey(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(32));
}

export const toHex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");

export async function hmacHex(key: Uint8Array, text: string): Promise<string> {
  const k = await crypto.subtle.importKey("raw", key as BufferSource, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return toHex(new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(text))));
}

export async function code(prefix: "t" | "c", text: string, key: Uint8Array): Promise<string> {
  return `${prefix}_${(await hmacHex(key, text)).slice(0, HEX_CHARS)}`;
}

/** Bits that differ between two hex digests of equal length. */
export function bitsDiffer(a: string, b: string): number {
  let n = 0;
  for (let i = 0; i < a.length; i++) {
    let x = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    while (x) { n += x & 1; x >>= 1; }
  }
  return n;
}

type Tok = { k: "ws" | "comment" | "str" | "num" | "param" | "ident" | "qident" | "op" | "punc"; v: string };

const RULES: [Tok["k"], RegExp][] = [
  ["ws", /^\s+/],
  ["comment", /^(--[^\n]*|\/\*[\s\S]*?\*\/)/],
  ["str", /^'(?:[^']|'')*'/],
  ["qident", /^"(?:[^"]|"")+"/],
  ["param", /^\$\d+/],
  ["num", /^\d+(?:\.\d+)?/],
  ["ident", /^[A-Za-z_][A-Za-z0-9_$]*/],
  ["op", /^(<=|>=|<>|!=|::|=|<|>|\|\|)/],
  ["punc", /^[(),.;*+\-/%]/],
];

export function tokenize(sql: string): Tok[] {
  const out: Tok[] = [];
  let s = sql;
  while (s) {
    const hit = RULES.map(([k, re]) => [k, re.exec(s)] as const).find(([, m]) => m);
    if (!hit) throw new Unparsed(`cannot read "${s.slice(0, 12)}"`);
    out.push({ k: hit[0], v: hit[1]![0] });
    s = s.slice(hit[1]![0].length);
  }
  return out;
}

export class Unparsed extends Error {}

const KEYWORDS = new Set(
  ("select from where and or not in is null as on join inner left right full outer cross group by order having limit offset " +
    "between like ilike distinct case when then else end asc desc union all exists interval true false with").split(" "),
);
const CLAUSES = new Set(["select", "from", "where", "group", "order", "having", "on", "limit"]);

export type Role = "EQ" | "JOIN" | "RANGE" | "GROUP" | "ORDER" | "SELECT";
export type HashedColumn = { table: string; column: string; code: string; tableCode: string; roles: Role[] };
export type HashResult = { sql: string; tables: { name: string; code: string }[]; columns: HashedColumn[]; values: number };

const name = (t: Tok) => (t.k === "qident" ? t.v.slice(1, -1).replace(/""/g, '"') : t.v.toLowerCase());

export async function hashSql(sql: string, key: Uint8Array): Promise<HashResult> {
  return (await hashParts(sql, key)).result;
}

/** One output token: `v` as the AI side sees it, `was` as written (value, table and column parts). */
type Part = { v: string; was: string; k: "" | "value" | "table" | "column" };
const KINDS = ["value", "table", "column"] as const;

/** Joins parts; kinds before `level` in KINDS are shown hashed. Ranges cover the `mark` kind's parts. */
function render(parts: Part[], level: number, mark?: Part["k"]) {
  let text = "";
  const changed: [number, number][] = [];
  const was: string[] = [];
  const ps = parts.at(-1)?.v === ";" ? parts.slice(0, -1) : parts;
  ps.forEach((p, i) => {
    const prev = ps[i - 1];
    if (prev && !/^[,)]/.test(p.v) && !prev.v.endsWith("(") && ![prev.v, p.v].some((x) => x === "::" || x === ".")) text += " ";
    const shown = p.k && KINDS.indexOf(p.k) < level ? p.v : p.was;
    if (mark && p.k === mark) { changed.push([text.length, text.length + shown.length]); was.push(p.was); }
    text += shown;
  });
  return { text, changed, was };
}

export type HashStep = { label: string; text: string; changed: [number, number][]; was: string[] };

/** The gateway's rewrite as five states: original, then comments, values, table names and column
 *  names replaced in turn. `changed` holds ranges in this step's text, `was` the previous step's
 *  text for each range (outside the ranges the two texts are equal). The last text is hashSql's. */
export async function hashSteps(sql: string, key: Uint8Array): Promise<HashStep[]> {
  const { parts } = await hashParts(sql, key);
  const clean = render(parts, 0).text;
  // Step 1 also normalises spacing and keyword case, so it is one prefix/suffix range.
  let a = 0;
  while (a < sql.length && a < clean.length && sql[a] === clean[a]) a++;
  let b = 0;
  while (b < sql.length - a && b < clean.length - a && sql.at(-1 - b) === clean.at(-1 - b)) b++;
  const steps: HashStep[] = [
    { label: "original", text: sql, changed: [], was: [] },
    { label: "comments removed", text: clean, changed: [[a, clean.length - b]], was: [sql.slice(a, sql.length - b)] },
  ];
  const labels = ["values become ?", "table names become t_ codes", "column names become c_ codes"];
  KINDS.forEach((k, i) => steps.push({ label: labels[i], ...render(parts, i + 1, k) }));
  return steps;
}

async function hashParts(sql: string, key: Uint8Array): Promise<{ result: HashResult; parts: Part[] }> {
  const toks = tokenize(sql).filter((t) => t.k !== "ws" && t.k !== "comment");
  const isId = (i: number) => toks[i] && (toks[i].k === "ident" || toks[i].k === "qident") && !(toks[i].k === "ident" && KEYWORDS.has(toks[i].v.toLowerCase()));
  const kw = (i: number, w: string) => toks[i]?.k === "ident" && toks[i].v.toLowerCase() === w;

  // Pass 1: tables after FROM (comma list) and JOIN, with their aliases.
  const role = new Array<string>(toks.length).fill(""); // "table" | "drop" | "col" | "qual"
  const alias = new Map<string, string>();
  for (let i = 0; i < toks.length; i++) {
    if (!(kw(i, "from") || kw(i, "join"))) continue;
    let j = i + 1;
    for (;;) {
      if (!isId(j) || toks[j + 1]?.v === "(") break; // subquery or function in FROM: not handled here
      const t = name(toks[j]);
      role[j] = "table";
      alias.set(t, t);
      j++;
      if (kw(j, "as")) { role[j] = "drop"; j++; }
      if (isId(j)) { alias.set(name(toks[j]), t); role[j] = "drop"; j++; }
      if (kw(i, "from") && toks[j]?.v === ",") { j++; continue; }
      break;
    }
  }
  const tables = [...new Set(alias.values())];
  if (!tables.length) throw new Unparsed("no table");

  // Pass 2: columns, roles and output.
  const cols = new Map<string, HashedColumn>();
  const out: Part[] = [];
  const other = (v: string): Part => ({ v, was: v, k: "" });
  let clause = "";
  const fnDepth: number[] = []; // paren depths opened by a function call
  let depth = 0;
  let values = 0; // literals and parameters replaced by ?
  const isValue = (t?: Tok) => !!t && (t.k === "str" || t.k === "num" || t.k === "param");
  const colAt = (i: number) => isId(i) && role[i] === "" && toks[i + 1]?.v !== "(" && toks[i + 1]?.v !== "." && toks[i - 1]?.v !== "::";

  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    const lower = t.v.toLowerCase();
    if (t.k === "ident" && CLAUSES.has(lower) && depth === 0) clause = lower;
    if (t.v === "(") {
      const fn = isId(i - 1) && role[i - 1] === "" && toks[i - 2]?.v !== "::";
      if (fn) { fnDepth.push(depth); out[out.length - 1].v += "("; out[out.length - 1].was += "("; } else out.push(other("("));
      depth++;
      continue;
    }
    if (t.v === ")") { depth--; if (fnDepth.at(-1) === depth) fnDepth.pop(); }

    if (role[i] === "drop") { if (out.at(-1)?.v === "AS") out.pop(); continue; }
    if (role[i] === "table") { out.push({ v: await code("t", name(t), key), was: t.v, k: "table" }); continue; }
    if (isValue(t)) { out.push({ v: "?", was: t.v, k: "value" }); values++; continue; }

    // Column alias in the select list (expr AS x): dropped, like the gateway's aliases.
    if (kw(i, "as") && clause === "select") { i++; continue; }

    let qual: string | null = null;
    let ci = i;
    if (isId(i) && toks[i + 1]?.v === "." && isId(i + 2)) { qual = name(t); ci = i + 2; }
    if (qual !== null || colAt(i)) {
      const colName = name(toks[ci]);
      let table: string;
      if (qual !== null) {
        const real = alias.get(qual);
        if (!real) throw new Unparsed(`unknown qualifier ${qual}`);
        table = real;
      } else {
        if (tables.length !== 1) throw new Unparsed(`column ${colName} could belong to ${tables.length} tables: qualify it (the gateway would ask its catalog)`);
        table = tables[0];
      }
      const c = await code("c", `${table}.${colName}`, key);
      const entry = cols.get(c) ?? { table, column: colName, code: c, tableCode: await code("t", table, key), roles: [] };
      cols.set(c, entry);
      const r = roleOf(toks, i, ci, clause, fnDepth.length > 0, isId);
      if (r && !entry.roles.includes(r)) entry.roles.push(r);
      out.push({ v: c, was: qual !== null ? `${t.v}.${toks[ci].v}` : t.v, k: "column" });
      i = ci;
      continue;
    }
    out.push(other(t.k === "ident" ? t.v.toUpperCase() : t.v));
  }
  const tableCodes = await Promise.all(tables.map(async (n) => ({ name: n, code: await code("t", n, key) })));
  return { result: { sql: render(out, KINDS.length).text, tables: tableCodes, columns: [...cols.values()], values }, parts: out };
}

/** Role of the column spanning tokens start..end, mirroring gateway/strip.py _role_of. */
function roleOf(toks: Tok[], start: number, end: number, clause: string, inFn: boolean, isId: (i: number) => boolean): Role | null {
  if (clause === "select") return "SELECT";
  if (clause === "group") return "GROUP";
  if (clause === "order") return "ORDER";
  if (inFn) return null; // a column wrapped in a function is not sargable
  const next = toks[end + 1]?.v.toLowerCase();
  const prev = toks[start - 1]?.v.toLowerCase();
  const otherIsColumn = (i: number) => isId(i) && toks[i + 1]?.v !== "(";
  if (next === "=" || next === "!=" || next === "<>") return otherIsColumn(end + 2) ? "JOIN" : "EQ";
  if (prev === "=" || prev === "!=" || prev === "<>") return otherIsColumn(start - 2) && toks[start - 2]?.v !== ")" ? "JOIN" : "EQ";
  if (next === "in") return "EQ";
  if (["<", "<=", ">", ">=", "between"].includes(next ?? "") || ["<", "<=", ">", ">="].includes(prev ?? "")) return "RANGE";
  return null;
}
