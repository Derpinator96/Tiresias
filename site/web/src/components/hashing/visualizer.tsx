"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Hash, KeyRound, Pencil, ShieldX } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CopyButton, Source } from "@/components/playground/bits";
import { Bento } from "@/components/viz/charts";
import { glitchFrame } from "@/lib/glitch";
import { HEX_CHARS, bitsDiffer, hashSql, hmacHex, newKey, toHex, Unparsed, type HashResult } from "@/lib/hashing";
import { cn } from "@/lib/utils";

// Neutral example names: public pages never show the demo database's real ones.
const EXAMPLE = "SELECT SUM(total) FROM invoices\nWHERE branch = 7 AND issued_on >= '2026-09-26' -- weekly report";
const TH = "px-2 py-1.5 text-xs font-medium uppercase tracking-wide text-slate-500";
export const BOX = "min-h-28 w-full whitespace-pre-wrap break-all rounded-lg px-2.5 py-2 font-mono text-xs";
export const PILL = "inline-flex h-7 items-center gap-1 pill px-3 text-sm";

/** Text that glitches from one string into another over `ms` (instant under reduced motion). */
export function useGlitch(initial: string): [string, (from: string, to: string, ms?: number) => void] {
  const [text, setText] = useState(initial);
  const raf = useRef(0);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  const play = useCallback((from: string, to: string, ms = 900) => {
    cancelAnimationFrame(raf.current);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { setText(to); return; }
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / ms);
      setText(glitchFrame(from, to, t, Math.random));
      if (t < 1) raf.current = requestAnimationFrame(step);
    };
    setText(from);
    raf.current = requestAnimationFrame(step);
  }, []);
  return [text, play];
}

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

export function HashingVisualizer() {
  const [key, setKey] = useState<Uint8Array | null>(null);
  const [sql, setSql] = useState(EXAMPLE);
  const [hashed, setHashed] = useState<HashResult | null>(null); // set while the box shows hashed SQL
  const [err, setErr] = useState<string | null>(null);
  const [shown, play] = useGlitch("");

  // The key must exist only in the browser. Made after mount: a lazy useState initializer would
  // differ between the prerendered HTML and the first client render (hydration mismatch).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setKey(newKey()), []);

  const run = async () => {
    if (!key) return;
    try {
      const r = await hashSql(sql, key);
      setErr(null);
      setHashed(r);
      play(sql, r.sql);
    } catch (e) {
      setErr(e instanceof Unparsed ? e.message : String(e)); // fail closed: no glitch, nothing shown
    }
  };
  const newDemoKey = () => { setHashed(null); setKey(newKey()); };

  return (
    <div className="space-y-3">
      <div className="glass-strong p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold text-slate-900">{hashed ? "What the AI side receives" : "Your SQL"}</span>
          <div className="ml-auto flex gap-2">
            {hashed ? (
              <>
                <button onClick={() => setHashed(null)} className={cn(PILL, "glass-subtle text-ink hover:bg-slate-200/70")}><Pencil className="size-3.5" /> Edit</button>
                <CopyButton text={hashed.sql} />
              </>
            ) : (
              <button onClick={run} disabled={!key} className={cn(PILL, "bg-ink font-medium text-white hover:bg-slate-800 disabled:opacity-50")}><Hash className="size-3.5" /> Hash it</button>
            )}
          </div>
        </div>
        {hashed ? (
          <pre aria-label="Hashed SQL" className={cn(BOX, "bg-(--inset-bg) text-ink")}>{shown}</pre>
        ) : (
          <Textarea
            value={sql}
            onChange={(e) => { setSql(e.target.value); setErr(null); }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void run(); } }}
            spellCheck={false}
            aria-label="SQL to hash"
            className={cn(BOX, "text-xs")}
          />
        )}
        <div className="mt-2 text-xs text-slate-600">
          {err ? (
            <span className="flex items-start gap-2 text-ink"><ShieldX className="size-4 shrink-0 text-signal" /> Not sent (fail closed): {err}</span>
          ) : hashed ? "Names are HMAC codes, values are ?, comments and aliases are gone." : "Enter hashes it, Shift+Enter adds a line."}
        </div>
        <Source>SIMPLIFIED: a tokenizer, not sqlglot (gateway/strip.py); no catalog, so an unqualified column with two tables in scope is refused. Codes use a demo key made in this tab.</Source>
      </div>

      {hashed && (
        <Bento className="grid-cols-3">
          <div className="tile-ink p-4 md:col-span-2"><div className="text-4xl font-light">{hashed.tables.length}</div><div className="text-xs text-white/60">tables hashed</div></div>
          <div className="glass p-4 md:col-span-2"><div className="text-4xl font-light text-ink">{hashed.columns.length}</div><div className="text-xs text-slate-500">columns hashed</div></div>
          <div className="glass p-4 md:col-span-2"><div className="text-4xl font-light text-ink">{hashed.values}</div><div className="text-xs text-slate-500">values stripped</div></div>
          <div className="glass col-span-3 p-4 md:col-span-6">
            <div className="mb-2 text-xs text-slate-500">roles sent with each column code</div>
            <div className="flex flex-wrap gap-1.5">
              {hashed.columns.map((c) => (
                <span key={c.code} className="glass-subtle pill px-2.5 py-1 font-mono text-xs text-ink">{c.code} <span className="text-slate-500">{c.roles.join(" ") || "none"}</span></span>
              ))}
            </div>
          </div>
        </Bento>
      )}

      <HowCodesAreMade keyBytes={key} sql={sql} onNewKey={newDemoKey} />
    </div>
  );
}

/** Collapsed: per-name codes with the HMAC steps, the demo key, and the one-letter avalanche. */
function HowCodesAreMade({ keyBytes: key, sql, onNewKey }: { keyBytes: Uint8Array | null; sql: string; onNewKey: () => void }) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [a, setA] = useState("branch");
  const [b, setB] = useState("brunch");
  const [res] = useAsync<HashResult | null>(async () => (open && key ? hashSql(sql, key) : null), [open, key, sql]);
  const names = res ? [...res.tables.map((t) => ({ text: t.name, code: t.code, roles: "table" })),
    ...res.columns.map((c) => ({ text: `${c.table}.${c.column}`, code: c.code, roles: c.roles.join(", ") || "none" }))] : [];
  const sel = names.find((n) => n.text === pick) ?? names[0];
  const [digest] = useAsync(async () => (key && sel ? hmacHex(key, sel.text) : ""), [key, sel?.text]);
  const [aval] = useAsync(async () => (open && key ? [await hmacHex(key, a), await hmacHex(key, b)] : null), [open, key, a, b]);

  return (
    <details className="glass p-4" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="cursor-pointer text-base font-semibold text-slate-900">How codes are made</summary>
      <div className="mt-3 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <KeyRound className="size-4 text-slate-700" />
          <div className="min-w-0 flex-1">
            <div className="text-xs text-slate-600">Demo key: 32 random bytes, made in this tab, never sent</div>
            <div className="truncate font-mono text-xs text-slate-900">{key ? `${toHex(key).slice(0, 24)}...` : "generating"}</div>
          </div>
          <button onClick={onNewKey} className={cn(PILL, "bg-ink font-medium text-white hover:bg-slate-800")}>New demo key</button>
        </div>

        {names.length > 0 && (
          <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <div className="max-h-72 overflow-auto rounded-lg">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-white"><tr><th className={TH}>hashed text</th><th className={TH}>code</th><th className={TH}>roles</th></tr></thead>
                <tbody className="font-mono text-xs">
                  {names.map((n) => (
                    <tr key={n.text} onClick={() => setPick(n.text)} className={cn("cursor-pointer even:bg-[#f6f7f9]", sel?.text === n.text && "bg-accent-soft even:bg-accent-soft")}>
                      <td className="px-2 py-1.5 text-slate-800">{n.text}</td><td className="px-2 text-slate-900">{n.code}</td><td className="px-2 text-slate-600">{n.roles}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sel && (
              <ol className="space-y-2 text-xs text-slate-700">
                <li><span className="text-slate-500">1. text:</span> <span className="font-mono text-slate-900">{sel.text}</span></li>
                <li><span className="text-slate-500">2. HMAC-SHA256(key, text):</span>
                  <div className="inset-field mt-1 break-all p-2 font-mono text-xs">
                    <span className="bg-accent-soft text-ink">{digest?.slice(0, HEX_CHARS)}</span><span className="text-slate-500">{digest?.slice(HEX_CHARS)}</span>
                  </div>
                </li>
                <li><span className="text-slate-500">3. keep the first {HEX_CHARS} hex characters</span> (config.yaml hashing.hmac_code_hex_chars)</li>
                <li><span className="text-slate-500">4. prefix t_ or c_:</span> <span className="font-mono text-slate-900">{sel.code}</span></li>
              </ol>
            )}
          </div>
        )}

        <div>
          <div className="mb-2 text-sm font-medium text-slate-900">Change one letter, get an unrelated code</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {([[a, setA], [b, setB]] as const).map(([v, set], i) => (
              <div key={i}>
                <Input value={v} onChange={(e) => set(e.target.value)} aria-label={`name ${i + 1}`} className="font-mono text-xs" />
                <div className="mt-1 font-mono text-xs text-slate-900">c_{aval?.[i]?.slice(0, HEX_CHARS)}</div>
              </div>
            ))}
          </div>
          {aval && <p className="mt-2 text-xs text-slate-600">{bitsDiffer(aval[0], aval[1])} of 256 digest bits differ (about 128 expected)</p>}
        </div>
      </div>
    </details>
  );
}
