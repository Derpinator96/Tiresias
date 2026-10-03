"use client";
import { useEffect, useState } from "react";
import { KeyRound, ShieldX } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Source, SqlBlock } from "@/components/playground/bits";
import { HEX_CHARS, bitsDiffer, hashSql, hmacHex, newKey, toHex, Unparsed, type HashResult } from "@/lib/hashing";
import { cn } from "@/lib/utils";

// Neutral example names: public pages never show the demo database's real ones.
const EXAMPLES = {
  "one table": "SELECT SUM(total) FROM invoices\nWHERE branch = 7 AND issued_on >= '2026-09-26' -- weekly report",
  "join": "SELECT s.city, COUNT(*) FROM shops s\nJOIN visits v ON s.id = v.shop\nWHERE v.kind IN ('walk-in', 'online') AND v.day >= $1\nGROUP BY s.city ORDER BY s.city",
};
const CATALOG = ["pk", "fk", "indexed", "nullable"] as const;

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): [T | null, string | null] {
  const [state, setState] = useState<[T | null, string | null]>([null, null]);
  useEffect(() => {
    let live = true;
    fn().then(
      (v) => live && setState([v, null]),
      (e) => live && setState([null, e instanceof Unparsed ? e.message : String(e)]),
    );
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** initialSql: the starting text; remount (key) to load another one. */
export function HashingVisualizer({ initialSql }: { initialSql?: string } = {}) {
  const [key, setKey] = useState<Uint8Array | null>(null);
  const [prevCodes, setPrevCodes] = useState<Set<string>>(new Set());
  const [sql, setSql] = useState(initialSql ?? EXAMPLES["one table"]);
  const [pick, setPick] = useState<string | null>(null);
  const [flags, setFlags] = useState<Record<string, Record<string, boolean>>>({});
  const [a, setA] = useState("branch");
  const [b, setB] = useState("brunch");

  // The key must exist only in the browser. Made after mount: a lazy useState initializer would
  // differ between the prerendered HTML and the first client render (hydration mismatch).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setKey(newKey()), []);

  const [res, err] = useAsync<HashResult | null>(async () => (key ? hashSql(sql, key) : null), [key, sql]);
  const names = res ? [...res.tables.map((t) => ({ kind: "table", text: t.name, code: t.code, roles: [] as string[] })),
    ...res.columns.map((c) => ({ kind: "column", text: `${c.table}.${c.column}`, code: c.code, roles: c.roles as string[] }))] : [];
  const sel = names.find((n) => n.text === pick) ?? names[0];
  const [digest] = useAsync(async () => (key && sel ? hmacHex(key, sel.text) : ""), [key, sel?.text]);
  const [aval] = useAsync(async () => (key ? [await hmacHex(key, a), await hmacHex(key, b)] : null), [key, a, b]);

  const regenerate = () => {
    setPrevCodes(new Set(names.map((n) => n.code)));
    setKey(newKey());
  };
  const changed = prevCodes.size && names.length ? names.filter((n) => !prevCodes.has(n.code)).length : null;
  const edit = (v: string) => { setSql(v); setPick(null); setPrevCodes(new Set()); };

  return (
    <div className="space-y-4">
      <div className="glass flex flex-wrap items-center gap-3 rounded-xl p-4">
        <KeyRound className="size-4 text-slate-700" />
        <div className="min-w-0 flex-1">
          <div className="text-xs text-slate-600">Demo key (32 random bytes, made in this tab, never sent)</div>
          <div className="truncate font-mono text-xs text-slate-900">{key ? `${toHex(key).slice(0, 24)}...` : "generating"}</div>
        </div>
        <button onClick={regenerate} className="h-8 rounded-md bg-ink px-3 text-xs font-medium text-white hover:bg-slate-800">New demo key</button>
        {changed !== null && <span className="text-xs text-slate-700">{changed} of {names.length} codes changed with the new key</span>}
      </div>

      <div className="glass rounded-xl p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-900">Your SQL</span>
          {Object.entries(EXAMPLES).map(([k, v]) => (
            <button key={k} onClick={() => edit(v)} className={cn("h-7 rounded-md border px-2 text-xs", sql === v ? "border-ink bg-ink text-white" : "glass-subtle text-ink hover:bg-white/70")}>
              Example: {k}
            </button>
          ))}
        </div>
        <Textarea value={sql} onChange={(e) => edit(e.target.value)} spellCheck={false} aria-label="SQL to hash" className="min-h-24 font-mono text-xs" />
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="min-w-0"><div className="mb-1 text-xs text-slate-600">What the operator sees</div><SqlBlock text={sql} /></div>
          <div className="min-w-0">
            <div className="mb-1 text-xs text-slate-600">What the AI side would receive</div>
            {err ? (
              <div className="flex items-start gap-2 rounded-lg bg-signal-soft p-3 text-xs font-medium text-signal"><ShieldX className="size-4 shrink-0" /> Not sent (fail closed): {err}</div>
            ) : <SqlBlock text={res?.sql ?? ""} />}
          </div>
        </div>
        <Source>SIMPLIFIED: a tokenizer, not sqlglot (gateway/strip.py); no catalog, so an unqualified column with two tables in scope is refused</Source>
      </div>

      {names.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          <div className="glass rounded-xl p-4">
            <div className="mb-2 text-sm font-semibold text-slate-900">Names and their codes</div>
            <div className="inset-field max-h-72 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-slate-50 text-slate-600"><tr><th className="px-2 py-1.5 font-medium">hashed text</th><th className="px-2 font-medium">code</th><th className="px-2 font-medium">roles</th></tr></thead>
                <tbody className="font-mono">
                  {names.map((n) => (
                    <tr key={n.text} onClick={() => setPick(n.text)} className={cn("cursor-pointer border-t border-slate-200/70 hover:bg-white/80", sel?.text === n.text && "bg-accent-soft/80")}>
                      <td className="px-2 py-1.5 text-slate-800">{n.text}</td>
                      <td className="px-2 text-slate-900">{n.code}</td>
                      <td className="px-2 text-slate-600">{n.roles.join(", ") || (n.kind === "table" ? "table" : "none")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Source>click a row for its steps; columns hash as table.column, so one name in two tables gets two codes</Source>
          </div>

          {sel && (
            <div className="glass rounded-xl p-4">
              <div className="mb-2 text-sm font-semibold text-slate-900">How {sel.code} is made</div>
              <ol className="space-y-2 text-xs text-slate-700">
                <li><span className="text-slate-500">1. text:</span> <span className="font-mono text-slate-900">{sel.text}</span></li>
                <li><span className="text-slate-500">2. HMAC-SHA256(key, text):</span>
                  <div className="inset-field mt-1 break-all p-2 font-mono text-xs">
                    <span className="bg-accent-soft text-ink">{digest?.slice(0, HEX_CHARS)}</span><span className="text-slate-500">{digest?.slice(HEX_CHARS)}</span>
                  </div>
                </li>
                <li><span className="text-slate-500">3. keep the first {HEX_CHARS} hex characters</span> (config.yaml hashing.hmac_code_hex_chars)</li>
                <li><span className="text-slate-500">4. prefix by kind:</span> <span className="font-mono text-slate-900">{sel.code}</span></li>
              </ol>
              <Source>without the key a guess cannot be checked; plain SHA-256 of the name gives another digest</Source>
            </div>
          )}
        </div>
      )}

      {res && res.columns.length > 0 && (
        <div className="glass rounded-xl p-4">
          <div className="mb-2 text-sm font-semibold text-slate-900">Column flags sent with each code</div>
          <div className="inset-field overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead className="text-slate-600"><tr><th className="px-2 py-1.5 font-medium">code</th>{CATALOG.map((f) => <th key={f} className="px-2 font-medium">{f}</th>)}<th className="px-2 font-medium">join</th><th className="px-2 font-medium">range</th><th className="px-2 font-medium">eq</th><th className="px-2 font-medium">bits</th></tr></thead>
              <tbody>
                {res.columns.map((c) => {
                  const f = flags[c.code] ?? {};
                  const derived = [c.roles.includes("JOIN"), c.roles.includes("RANGE"), c.roles.includes("EQ")];
                  const bits = [...CATALOG.map((k) => !!f[k]), ...derived].map((x) => (x ? 1 : 0)).join("");
                  return (
                    <tr key={c.code} className="border-t border-slate-200/70">
                      <td className="px-2 py-1.5 font-mono text-slate-900">{c.code}</td>
                      {CATALOG.map((k) => (
                        <td key={k} className="px-2">
                          <Checkbox aria-label={`${k} for ${c.code}`} checked={!!f[k]} onCheckedChange={(v) => setFlags({ ...flags, [c.code]: { ...f, [k]: !!v } })} />
                        </td>
                      ))}
                      {derived.map((d, i) => <td key={i} className="px-2 font-mono">{d ? "yes" : "no"}</td>)}
                      <td className="px-2 font-mono text-slate-900">{bits}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Source>pk, fk, indexed, nullable come from the catalog (tick them here); join, range, eq from the SQL; the gateway sends named booleans, not bits (gateway/ingest/stats.py)</Source>
        </div>
      )}

      <div className="glass rounded-xl p-4">
        <div className="mb-2 text-sm font-semibold text-slate-900">Change one letter, get an unrelated code</div>
        <div className="grid gap-3 sm:grid-cols-2">
          {[[a, setA], [b, setB]].map(([v, set], i) => (
            <div key={i}>
              <Input value={v as string} onChange={(e) => (set as (s: string) => void)(e.target.value)} aria-label={`name ${i + 1}`} className="font-mono text-xs" />
              <div className="mt-1 font-mono text-xs text-slate-900">c_{aval?.[i]?.slice(0, HEX_CHARS)}</div>
            </div>
          ))}
        </div>
        {aval && <p className="mt-2 text-xs text-slate-700">{bitsDiffer(aval[0], aval[1])} of 256 digest bits differ (about 128 expected)</p>}
      </div>
    </div>
  );
}
