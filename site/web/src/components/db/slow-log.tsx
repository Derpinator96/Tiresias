"use client";
// /slow-log: pg-prod's slow templates from GET /api/db/slow-log and the slowest plan-generation
// templates from data/plans/web_sample.json (both through the local API; the source holds no
// query text or figure). "Generate one" draws from GET /api/db/slow-log/random.
import { useState } from "react";
import { Dices } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorLine, LocalOnly, ms, useJson } from "@/components/db/local";
import { SqlBlock, Stat } from "@/components/playground/bits";
import { ChartCard, HBars, SERIES } from "@/components/viz/charts";
import { LOCAL } from "@/lib/context";
import { cn } from "@/lib/utils";

type Prod = { template_id: string; sql: string; calls: number; mean_ms: number; total_ms: number; slow: boolean; example?: string };
type Bench = { database: string; template_id: string; demo: boolean; sql: string | null; plans: number; median_runtime_ms: number | null; max_runtime_ms: number | null; timed_out: number; nodes: number | null; top_ops: string[] };
type Log = { threshold_ms: number | null; templates: Prod[]; gateway_error?: string; bench: Bench[]; bench_note: string; bench_error?: string };
type Drawn = ({ source: "pg-prod" } & Prod) | ({ source: "bench" } & Bench);
type Pick = Drawn & { pool: { "pg-prod": number; bench: number } };

const BENCH_LABEL = "plan generation workload (data/plans), not pg-prod's log";
const KEEP = 5;

const SlowBadge = ({ on }: { on: boolean }) => (on ? <Badge className="bg-orange-600 text-white">slow</Badge> : <Badge variant="outline">ok</Badge>);

function BenchCard({ e, className }: { e: Bench; className?: string }) {
  return (
    <section className={cn("glass rounded-xl p-4", className)}>
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono">{e.database}</Badge>
        <span className="font-mono text-sm font-semibold text-slate-900">{e.template_id}</span>
        {e.demo && <Badge variant="outline">demo query</Badge>}
        <span className="text-[11px] text-slate-500">{BENCH_LABEL}</span>
      </header>
      {e.sql ? <SqlBlock text={e.sql} /> : <p className="text-xs text-slate-500">no query text for this template</p>}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="median" value={ms(e.median_runtime_ms)} />
        <Stat label="max" value={ms(e.max_runtime_ms)} />
        <Stat label="plans" value={String(e.plans)} />
        <Stat label="timed out" value={String(e.timed_out)} />
        <Stat label="nodes" value={e.nodes === null ? "n/a" : String(e.nodes)} />
        <Stat label="top ops" value={e.top_ops.join(", ") || "n/a"} />
      </div>
    </section>
  );
}

function ProdCard({ e, threshold, className }: { e: Prod; threshold: number | null; className?: string }) {
  return (
    <section className={cn("glass rounded-xl p-4", className)}>
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-mono">pg-prod</Badge>
        <span className="font-mono text-sm font-semibold text-slate-900">{e.template_id}</span>
        <SlowBadge on={e.slow} />
        {threshold !== null && <span className="text-[11px] text-slate-500">slow means mean above {threshold} ms</span>}
      </header>
      <SqlBlock text={e.example ?? e.sql} />
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat label="calls" value={e.calls.toLocaleString()} />
        <Stat label="mean" value={ms(e.mean_ms)} />
        <Stat label="total" value={ms(e.total_ms)} />
      </div>
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
    <div className="mt-6 space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={draw} disabled={busy}><Dices /> Generate one</Button>
        <span className="text-sm text-slate-700">
          slow threshold: <span className="font-mono font-semibold text-slate-900">{threshold === null ? "n/a" : `${threshold} ms`}</span>
          {data && <span className="text-xs text-slate-500"> ({prod.length} pg-prod templates, {data.bench.length} benchmark templates listed)</span>}
        </span>
      </div>
      <ErrorLine text={error} />
      <ErrorLine text={drawError} />
      {latest && (
        <div>
          <p className="mb-2 text-xs text-slate-600">
            drawn from {latest.source}; pools: {latest.pool["pg-prod"]} pg-prod, {latest.pool.bench} benchmark; pick proportional to pool size
          </p>
          {latest.source === "pg-prod"
            ? <ProdCard e={latest} threshold={threshold} className="glass-strong ring-2 ring-blue-500" />
            : <BenchCard e={latest} className="glass-strong ring-2 ring-blue-500" />}
          {older.length > 0 && (
            <div className="mt-3 space-y-3 opacity-80">
              {older.map((d, i) => (d.source === "pg-prod" ? <ProdCard key={i} e={d} threshold={threshold} /> : <BenchCard key={i} e={d} />))}
            </div>
          )}
        </div>
      )}

      <h2 className="text-lg font-semibold tracking-tight text-slate-900">pg-prod slow log</h2>
      <ErrorLine text={data?.gateway_error} />
      {prod.length > 0 && (
        <ChartCard title="Mean time per pg-prod template" caption="mean_ms per template, /v1/private/slow-log (pg_stat_statements); dashed line: config.yaml slow_query_ms">
          <HBars
            bars={prod.map((t) => ({ label: t.template_id, value: t.mean_ms, color: t.slow ? SERIES.orange : SERIES.blue, note: `${t.calls} calls, ${ms(t.total_ms)} total` }))}
            unit=" ms"
            refLine={threshold === null ? undefined : { value: threshold, label: `slow at ${threshold} ms` }}
          />
        </ChartCard>
      )}
      {prod.length > 0 && (
        <div className="glass rounded-xl p-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>template</TableHead><TableHead>query</TableHead>
                <TableHead className="text-right">calls</TableHead><TableHead className="text-right">mean</TableHead><TableHead className="text-right">total</TableHead><TableHead>state</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {prod.map((t) => (
                <TableRow key={t.template_id}>
                  <TableCell className="align-top font-mono text-xs">{t.template_id}</TableCell>
                  <TableCell className="min-w-72 max-w-2xl align-top"><pre className="whitespace-pre-wrap font-mono text-[11px] leading-snug text-slate-800 [overflow-wrap:anywhere]">{t.sql}</pre></TableCell>
                  <TableCell className="text-right align-top font-mono text-xs">{t.calls.toLocaleString()}</TableCell>
                  <TableCell className="text-right align-top font-mono text-xs">{ms(t.mean_ms)}</TableCell>
                  <TableCell className="text-right align-top font-mono text-xs">{ms(t.total_ms)}</TableCell>
                  <TableCell className="align-top"><SlowBadge on={t.slow} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {data && !data.gateway_error && !prod.length && <p className="text-sm text-slate-600">the slow log holds no template yet</p>}

      <h2 className="text-lg font-semibold tracking-tight text-slate-900">Benchmark plans (DSB, TPC-H, demo database copy)</h2>
      <p className="text-xs text-slate-600">{BENCH_LABEL}{data?.bench_note ? `; ${data.bench_note}` : ""}</p>
      <ErrorLine text={data?.bench_error} />
      <div className="space-y-3">{data?.bench.map((e) => <BenchCard key={`${e.database}/${e.template_id}`} e={e} />)}</div>
    </div>
  );
}
