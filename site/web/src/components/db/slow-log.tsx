"use client";
// /slow-log: pg-prod's slow templates from GET /api/db/slow-log and the slowest plan-generation
// templates from data/plans/web_sample.json (both through the local API; the source holds no
// query text or figure). "Generate one" draws from GET /api/db/slow-log/random.
import { useState } from "react";
import { Dices } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ErrorLine, LocalOnly, ms, useJson } from "@/components/db/local";
import { Source, SqlBlock } from "@/components/playground/bits";
import { Bento, ChartCard, HBars, SERIES } from "@/components/viz/charts";
import { LOCAL } from "@/lib/context";
import { cn } from "@/lib/utils";

type Prod = { template_id: string; sql: string; calls: number; mean_ms: number; total_ms: number; slow: boolean; example?: string };
type Bench = { database: string; template_id: string; demo: boolean; sql: string | null; plans: number; median_runtime_ms: number | null; max_runtime_ms: number | null; timed_out: number; nodes: number | null; top_ops: string[] };
type Log = { threshold_ms: number | null; templates: Prod[]; gateway_error?: string; bench: Bench[]; bench_note: string; bench_error?: string };
type Drawn = ({ source: "pg-prod" } & Prod) | ({ source: "bench" } & Bench);
type Pick = Drawn & { pool: { "pg-prod": number; bench: number } };

const BENCH_LABEL = "plan-generation workload (data/plans), not pg-prod's log";
const KEEP = 5;
const tag = "pill text-xs";

// slow is a data state (signal); ok is structure (slate)
const SlowBadge = ({ on }: { on: boolean }) => (on ? <Badge className={cn(tag, "bg-signal text-white")}>slow</Badge> : <Badge variant="secondary" className={cn(tag, "text-slate-600")}>ok</Badge>);

/** Small figure grid for a compact tile: label over a mono value. */
function Figs({ items, dark }: { items: [string, string][]; dark?: boolean }) {
  return (
    <dl className="grid grid-cols-3 gap-x-3 gap-y-1">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className={cn("text-xs", dark ? "text-white/60" : "text-slate-500")}>{k}</dt>
          <dd className={cn("truncate font-mono text-sm font-semibold", dark ? "text-white" : "text-slate-900")}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

const benchFigs = (e: Bench): [string, string][] => [["median", ms(e.median_runtime_ms)], ["max", ms(e.max_runtime_ms)], ["plans", String(e.plans)], ["timed out", String(e.timed_out)], ["nodes", e.nodes === null ? "n/a" : String(e.nodes)]];
const prodFigs = (e: Prod): [string, string][] => [["calls", e.calls.toLocaleString()], ["mean", ms(e.mean_ms)], ["total", ms(e.total_ms)]];

function BenchCard({ e }: { e: Bench }) {
  return (
    <section className="glass flex min-w-0 flex-col gap-2 p-4 md:col-span-4">
      <header className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className={cn(tag, "font-mono text-slate-600")}>{e.database}</Badge>
        <span className="font-mono text-sm font-semibold text-slate-900">{e.template_id}</span>
        {e.demo && <Badge variant="secondary" className={cn(tag, "text-slate-600")}>demo query</Badge>}
      </header>
      {e.sql ? <div className="max-h-32 overflow-auto rounded-xl"><SqlBlock text={e.sql} /></div> : <p className="text-xs text-slate-500">no query text for this template</p>}
      <Figs items={benchFigs(e)} />
      <div className="truncate text-xs text-slate-600" title={e.top_ops.join(", ")}>top ops: <span className="font-mono text-slate-900">{e.top_ops.join(", ") || "n/a"}</span></div>
    </section>
  );
}

function ProdCard({ e }: { e: Prod }) {
  return (
    <section className="glass flex min-w-0 flex-col gap-2 p-4 md:col-span-4">
      <header className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className={cn(tag, "font-mono text-slate-600")}>pg-prod</Badge>
        <span className="font-mono text-sm font-semibold text-slate-900">{e.template_id}</span>
        <SlowBadge on={e.slow} />
      </header>
      <div className="max-h-32 overflow-auto rounded-xl"><SqlBlock text={e.sql} /></div>
      <Figs items={prodFigs(e)} />
    </section>
  );
}

export function SlowLog() {
  const { data, error } = useJson<Log>(LOCAL ? "/api/db/slow-log" : null);
  const [drawn, setDrawn] = useState<Pick[]>([]);
  const [drawError, setDrawError] = useState<string>();
  const [busy, setBusy] = useState(false);
  if (!LOCAL) return <LocalOnly />;

  const draw = async () => {
    setBusy(true);
    setDrawError(undefined);
    try {
      const r = await fetch("/api/db/slow-log/random", { cache: "no-store" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.error ?? `HTTP ${r.status}`);
      setDrawn((d) => [body as Pick, ...d].slice(0, KEEP));
    } catch (e) {
      setDrawError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const prod = [...(data?.templates ?? [])].sort((a, b) => b.total_ms - a.total_ms);
  const threshold = data?.threshold_ms ?? null;
  const [latest, ...older] = drawn;
  return (
    <div className="mt-6 space-y-3">
      <ErrorLine text={error} />
      <Bento>
        <div className="min-w-0 md:col-span-7">
          {prod.length > 0 ? (
            <ChartCard className="h-full" title="Mean time per pg-prod template" caption="mean_ms per template, /v1/private/slow-log (pg_stat_statements); dashed line: config.yaml slow_query_ms">
              <HBars
                bars={prod.map((t) => ({ label: t.template_id, value: t.mean_ms, color: t.slow ? SERIES.orange : SERIES.blue, note: `${t.calls} calls, ${ms(t.total_ms)} total` }))}
                unit=" ms"
                refLine={threshold === null ? undefined : { value: threshold, label: `slow at ${threshold} ms` }}
              />
            </ChartCard>
          ) : (
            <div className="glass h-full p-5 text-sm text-slate-600">
              <ErrorLine text={data?.gateway_error} />
              {data && !data.gateway_error && "the slow log holds no template yet"}
            </div>
          )}
        </div>

        <section className="tile-ink flex min-w-0 flex-col gap-3 p-5 md:col-span-5">
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={draw} disabled={busy} className="inline-flex h-9 items-center gap-1.5 pill bg-lime px-4 text-sm font-medium text-ink disabled:opacity-40"><Dices className="size-4" /> Generate one</button>
            <span className="text-xs text-white/60">slow at <span className="font-mono text-white">{threshold === null ? "n/a" : `${threshold} ms`}</span>{data && `; ${prod.length} pg-prod, ${data.bench.length} benchmark`}</span>
          </div>
          <ErrorLine text={drawError} />
          {latest ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="pill bg-white/10 px-2.5 py-0.5 font-mono text-xs text-white/80">{latest.source === "pg-prod" ? "pg-prod" : latest.database}</span>
                <span className="font-mono text-sm font-semibold">{latest.template_id}</span>
                {latest.source === "pg-prod" ? <SlowBadge on={latest.slow} /> : <span className="text-xs text-white/60">plan-generation workload</span>}
              </div>
              <pre className="max-h-48 overflow-auto rounded-xl bg-white/10 p-3 font-mono text-xs leading-relaxed text-white/90 [overflow-wrap:anywhere] whitespace-pre-wrap">{(latest.source === "pg-prod" ? latest.example ?? latest.sql : latest.sql) ?? "no query text for this template"}</pre>
              <Figs dark items={latest.source === "pg-prod" ? prodFigs(latest) : benchFigs(latest)} />
              {older.length > 0 && (
                <ol className="space-y-0.5 text-xs text-white/60">
                  {older.map((d, i) => <li key={i} className="truncate font-mono">{d.source} {d.template_id} {d.source === "pg-prod" ? ms(d.mean_ms) : ms(d.median_runtime_ms)}</li>)}
                </ol>
              )}
              <details className="text-xs text-white/60"><summary className="cursor-pointer">source and assumptions</summary>pools: {latest.pool["pg-prod"]} pg-prod, {latest.pool.bench} benchmark; pick proportional to pool size</details>
            </>
          ) : (
            <p className="text-sm text-white/70">Draws one template from pg-prod&apos;s slow log or the benchmark plans.</p>
          )}
        </section>
      </Bento>

      {prod.length > 0 && <h2 className="pt-3 text-lg font-semibold tracking-tight text-slate-900">pg-prod slow log</h2>}
      {prod.length > 0 && <Bento>{prod.map((t) => <ProdCard key={t.template_id} e={t} />)}</Bento>}
      {prod.length > 0 && <ErrorLine text={data?.gateway_error} />}

      <h2 className="pt-3 text-lg font-semibold tracking-tight text-slate-900">Benchmark plans (DSB, TPC-H, demo database copy)</h2>
      <Source>{BENCH_LABEL}{data?.bench_note ? `; ${data.bench_note}` : ""}</Source>
      <ErrorLine text={data?.bench_error} />
      <Bento>{data?.bench.map((e) => <BenchCard key={`${e.database}/${e.template_id}`} e={e} />)}</Bento>
    </div>
  );
}
