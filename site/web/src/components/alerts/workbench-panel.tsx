"use client";
// The query workbench (analyst and DBA roles): suggested slow-log and normal queries, a burst
// button and own SQL. Every run is recorded for the analytics dashboard. Local web app only.
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Play, Triangle, Zap } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Source } from "@/components/playground/bits";
import { Bad } from "@/components/ask/data-ask";
import { Bento } from "@/components/viz/charts";
import { LOCAL } from "@/lib/context";
import type { QueryEvent } from "@/lib/analytics-shared";

type Me = { email: string; name: string; role: "dba" | "analyst" };
type Suggestion = { id: string; label: string; sql: string; mean_ms?: number; calls?: number };
type Run = { event: QueryEvent; columns: string[]; rows: unknown[][]; truncated: boolean };
const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const cell = (v: unknown) => (v === null || v === undefined ? "null" : typeof v === "number" ? n(v) : String(v));
const BURST = 8;

export function WorkbenchPanel() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [sugg, setSugg] = useState<{ slow: Suggestion[]; normal: Suggestion[]; threshold_ms: number | null }>({ slow: [], normal: [], threshold_ms: null });
  const [runs, setRuns] = useState<Run[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [own, setOwn] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch("/api/auth/me", { cache: "no-store" });
    if (!r.ok) return setMe(null);
    setMe(await r.json());
    const s = await fetch("/api/workbench/suggestions", { cache: "no-store" });
    if (s.ok) setSugg(await s.json());
  }, []);
  useEffect(() => {
    if (!LOCAL) return;
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  const run = async (q: { sql: string; label: string; kind: "slow" | "normal" | "own" }, key: string) => {
    setBusy(key);
    setErr(null);
    const r = await fetch("/api/workbench/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(q) });
    const body = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    setBusy(null);
    if (!r.ok) { setErr(body.error); return; }
    setRuns((x) => [body, ...x].slice(0, 30));
    if (!body.event.ok) setErr(`The query failed: ${body.event.error}`);
  };
  const burst = async () => {
    const pool = [...sugg.slow.map((s) => ({ ...s, kind: "slow" as const })), ...sugg.normal.map((s) => ({ ...s, kind: "normal" as const }))];
    for (let i = 0; i < BURST && pool.length; i++) {
      const q = pool[Math.floor(Math.random() * pool.length)];
      await run({ sql: q.sql, label: q.label, kind: q.kind }, "burst");
    }
  };

  if (!LOCAL) return <p className="text-sm text-slate-700">The workbench exists only in the local web app.</p>;
  if (me === undefined) return <p className="mt-6 flex items-center gap-2 text-sm text-slate-600"><Loader2 className="size-4 animate-spin" /> Loading</p>;
  if (me === null) {
    return (
      <div className="glass mt-6 max-w-md space-y-3 p-6">
        <p className="text-sm text-slate-800">Sign in to run queries. Analysts and DBAs can use the workbench.</p>
        <div className="flex gap-2">
          <Link href="/signin?next=%2Fworkbench" className="inline-flex h-9 items-center pill bg-ink px-4 text-sm font-medium text-white">Sign in</Link>
          <Link href="/signup?next=%2Fworkbench" className="glass-subtle inline-flex h-9 items-center pill px-4 text-sm font-medium text-ink">Create account</Link>
        </div>
      </div>
    );
  }

  const list = (title: string, note: string, items: Suggestion[], kind: "slow" | "normal") => (
    <section className="glass min-w-0 space-y-2 p-5 md:col-span-6">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <p className="text-xs text-slate-600">{note}</p>
      <ul className="space-y-1.5">
        {items.map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <button type="button" disabled={!!busy} onClick={() => void run({ sql: s.sql, label: s.label, kind }, s.id)} aria-label={`Run ${s.label}`}
              className="inline-flex size-8 shrink-0 items-center justify-center pill bg-ink text-white hover:bg-slate-800 disabled:opacity-40">
              {busy === s.id ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-3.5" />}
            </button>
            <span className="min-w-0 flex-1 truncate text-sm text-slate-800" title={s.sql}>{s.label}</span>
            {s.mean_ms !== undefined && <span className="shrink-0 font-mono text-xs text-slate-600">{n(s.mean_ms)} ms avg</span>}
          </li>
        ))}
        {!items.length && <li className="text-sm text-slate-600">None right now.</li>}
      </ul>
    </section>
  );

  const last = runs[0];
  const spike = (ms: number) => sugg.threshold_ms !== null && ms >= sugg.threshold_ms;   // config.yaml workload.slow_query_ms via the gateway
  return (
    <Bento className="mt-6">
      <section className="tile-ink flex flex-wrap items-center gap-3 p-5 md:col-span-12">
        <div className="min-w-0 flex-1">
          <div className="text-sm text-white/70">Signed in as {me.name}, {me.email}, role <span className="font-semibold text-lime">{me.role}</span></div>
          <div className="text-xs text-white/50">every run goes read-only through the gateway and shows up on the DBA&apos;s analytics dashboard</div>
        </div>
        <button type="button" disabled={!!busy} onClick={() => void burst()} className="inline-flex h-10 items-center gap-2 pill bg-lime px-5 text-sm font-semibold text-ink disabled:opacity-50">
          {busy === "burst" ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />} Run a burst of {BURST}
        </button>
      </section>
      {list("Slow-log queries", "From pg-prod's slow log: the latest logged query of each slow template. These cause the spikes.", sugg.slow, "slow")}
      {list("Normal queries", "Fast lookups, timed at 10 to 45 ms when they were chosen.", sugg.normal, "normal")}
      <section className="glass min-w-0 space-y-2 p-5 md:col-span-12">
        <h3 className="text-base font-semibold text-slate-900">Your own SQL</h3>
        <Textarea value={own} onChange={(e) => setOwn(e.target.value)} rows={3} placeholder="SELECT ... (one read-only SELECT; writes are refused)" className="font-mono text-sm" />
        <button type="button" disabled={!own.trim() || !!busy} onClick={() => void run({ sql: own, label: "own SQL", kind: "own" }, "own")}
          className="inline-flex h-8 items-center gap-1.5 pill bg-ink px-3.5 text-sm font-medium text-white disabled:opacity-40">
          {busy === "own" ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />} Run
        </button>
      </section>
      {err && <div className="md:col-span-12"><Bad>{err}</Bad></div>}
      {last && last.event.ok && (
        <section className="glass min-w-0 p-5 md:col-span-12">
          <div className="mb-2 flex flex-wrap items-baseline gap-3">
            <h3 className="text-base font-semibold text-slate-900">{last.event.label}</h3>
            <span className="font-mono text-sm text-ink">{n(last.event.ms)} ms</span>
            {spike(last.event.ms) && <span className="inline-flex items-center gap-1 text-sm font-semibold text-signal"><Triangle className="size-3.5 fill-current" /> spike</span>}
          </div>
          <div className="max-h-72 overflow-auto">
            <Table>
              <TableHeader><TableRow>{last.columns.map((c) => <TableHead key={c} className="text-xs uppercase tracking-wide text-slate-500">{c.replace(/_/g, " ")}</TableHead>)}</TableRow></TableHeader>
              <TableBody>{last.rows.map((row, i) => <TableRow key={i}>{row.map((v, j) => <TableCell key={j} className="font-mono text-xs">{cell(v)}</TableCell>)}</TableRow>)}</TableBody>
            </Table>
          </div>
          <Source>first 10 rows; time measured by the gateway around the query, connection included</Source>
        </section>
      )}
      {runs.length > 0 && (
        <section className="glass min-w-0 p-5 md:col-span-12">
          <h3 className="mb-2 text-base font-semibold text-slate-900">Your runs</h3>
          <ul className="space-y-1 text-sm">
            {runs.map((r, i) => (
              <li key={i} className="flex gap-3">
                <span className="shrink-0 font-mono text-xs text-slate-500">{new Date(r.event.t).toLocaleTimeString("en-GB")}</span>
                <span className="min-w-0 flex-1 truncate text-slate-800">{r.event.label}</span>
                <span className={spike(r.event.ms) ? "shrink-0 font-mono text-xs font-semibold text-signal" : "shrink-0 font-mono text-xs text-slate-600"}>{r.event.ok ? `${n(r.event.ms)} ms` : "failed"}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Bento>
  );
}
