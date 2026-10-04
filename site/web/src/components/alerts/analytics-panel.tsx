"use client";
// Live query analytics for DBAs: every workbench run as a point in time, spikes (runs at or over
// the slow threshold) marked, polled every analytics.poll_ms. Local web app only.
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Loader2, Triangle } from "lucide-react";
import { Source } from "@/components/playground/bits";
import { Bento } from "@/components/viz/charts";
import { LOCAL } from "@/lib/context";
import { isSpike, summarize, type QueryEvent } from "@/lib/analytics-shared";

type Data = { config: { poll_ms: number; window_minutes: number; threshold_ms: number }; now: number; events: QueryEvent[] };
const INK = "#262726", SIGNAL = "#ea580c", GRID = "#e4e7e4";
const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const hms = (t: number) => new Date(t).toLocaleTimeString("en-GB");

/** Query time over clock time, one series; spikes as signal triangles with a "spike" label on the latest three. */
function Timeline({ events, threshold, from, to }: { events: QueryEvent[]; threshold: number; from: number; to: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 960, H = 300, L = 52, R = 16, T = 20, B = 30;
  const pts = events.filter((e) => e.ok);
  const yMax = Math.max(threshold * 1.6, ...pts.map((e) => e.ms)) * 1.1;
  const x = (t: number) => L + ((t - from) / Math.max(1, to - from)) * (W - L - R);
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);
  const yTicks = [0, Math.round(yMax / 2), Math.round(yMax)];
  const xTicks = Array.from({ length: 5 }, (_, i) => from + ((to - from) * i) / 4);
  const spikes = pts.filter((e) => e.ms >= threshold);
  // label at most three spikes, the largest first, never two within 90 px (bursts land in one second)
  const labelled = new Set<QueryEvent>();
  for (const e of [...spikes].sort((a, b) => b.ms - a.ms)) {
    if (labelled.size < 3 && [...labelled].every((o) => Math.abs(x(o.t) - x(e.t)) >= 90)) labelled.add(e);
  }
  const near = (clientX: number, rect: DOMRect) => {
    const t = from + ((clientX - rect.left) / rect.width * W - L) / (W - L - R) * (to - from);
    let best = -1, d = Infinity;
    pts.forEach((e, i) => { const k = Math.abs(e.t - t); if (k < d) { d = k; best = i; } });
    return best < 0 ? null : best;
  };
  const h = hover !== null ? pts[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`query time in ms over time; ${spikes.length} spikes at or over ${threshold} ms`}
        onMouseMove={(ev) => setHover(near(ev.clientX, ev.currentTarget.getBoundingClientRect()))} onMouseLeave={() => setHover(null)}>
        {yTicks.map((t) => (
          <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={GRID} /><text x={L - 8} y={y(t) + 4} textAnchor="end" className="fill-slate-500 text-xs">{t} ms</text></g>
        ))}
        {xTicks.map((t) => <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="fill-slate-500 text-xs">{hms(t)}</text>)}
        <line x1={L} x2={W - R} y1={y(threshold)} y2={y(threshold)} stroke="#64748b" strokeDasharray="5 4" />
        <text x={L + 6} y={y(threshold) - 6} className="fill-slate-600 text-xs">slow: {threshold} ms</text>
        {pts.length > 1 && <polyline points={pts.map((e) => `${x(e.t)},${y(e.ms)}`).join(" ")} fill="none" stroke={INK} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
        {pts.map((e, i) => e.ms >= threshold ? (
          <g key={i}>
            <path d={`M ${x(e.t)} ${y(e.ms) - 8} L ${x(e.t) + 7} ${y(e.ms) + 5} L ${x(e.t) - 7} ${y(e.ms) + 5} Z`} fill={SIGNAL} stroke="white" strokeWidth={2} />
            {labelled.has(e) && <text x={x(e.t)} y={y(e.ms) - 13} textAnchor="middle" className="fill-slate-900 text-xs font-semibold">spike {n(e.ms)} ms</text>}
          </g>
        ) : <circle key={i} cx={x(e.t)} cy={y(e.ms)} r={4} fill={INK} stroke="white" strokeWidth={2} />)}
        {h && <line x1={x(h.t)} x2={x(h.t)} y1={T} y2={H - B} stroke="#94a3b8" strokeDasharray="2 3" />}
      </svg>
      {h && (
        <div className="glass-strong pointer-events-none absolute top-2 max-w-72 rounded-lg px-3 py-2 text-xs text-slate-800"
          style={{ left: `${(x(h.t) / W) * 100}%`, transform: x(h.t) > W * 0.7 ? "translateX(-105%)" : "translateX(8px)" }}>
          <div className="font-mono font-semibold">{n(h.ms)} ms{h.ms >= threshold && " (spike)"}</div>
          <div>{hms(h.t)}, {h.user}</div>
          <div className="truncate">{h.label}</div>
        </div>
      )}
      <table className="sr-only"><thead><tr><th>time</th><th>user</th><th>query</th><th>ms</th></tr></thead>
        <tbody>{pts.map((e, i) => <tr key={i}><td>{hms(e.t)}</td><td>{e.user}</td><td>{e.label}</td><td>{e.ms}</td></tr>)}</tbody></table>
    </div>
  );
}

export function AnalyticsPanel() {
  const [me, setMe] = useState<{ email: string; role: string } | null | undefined>(undefined);
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const poll = useCallback(async () => {
    const r = await fetch("/api/analytics", { cache: "no-store" });
    const body = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    if (!r.ok) { setErr(body.error); return null; }
    setErr(null);
    setData(body);
    return body as Data;
  }, []);

  useEffect(() => {
    if (!LOCAL) return;
    let stop = false, id = 0;
    const tick = async () => {
      const d = await poll();
      if (!stop && d) id = window.setTimeout(tick, d.config.poll_ms);
    };
    const start = async () => {
      const r = await fetch("/api/auth/me", { cache: "no-store" });
      const m = r.ok ? await r.json() : null;
      if (stop) return;
      setMe(m);
      if (m?.role === "dba") void tick();
    };
    id = window.setTimeout(() => void start(), 0);
    return () => { stop = true; clearTimeout(id); };
  }, [poll]);

  const sum = useMemo(() => data && summarize(data.events, data.config.threshold_ms, data.now), [data]);

  if (!LOCAL) return <p className="text-sm text-slate-700">Analytics exist only in the local web app.</p>;
  if (me === undefined) return <p className="mt-6 flex items-center gap-2 text-sm text-slate-600"><Loader2 className="size-4 animate-spin" /> Loading</p>;
  if (me === null) {
    return (
      <div className="glass mt-6 max-w-md space-y-3 p-6">
        <p className="text-sm text-slate-800">Sign in as a DBA to see query analytics.</p>
        <Link href="/signin?next=%2Fanalytics" className="inline-flex h-9 items-center pill bg-ink px-4 text-sm font-medium text-white">Sign in</Link>
      </div>
    );
  }
  if (me.role !== "dba") return <div className="glass mt-6 max-w-lg p-6 text-sm text-slate-800">Signed in as {me.email} with the {me.role} role. Analytics are for DBAs; your queries appear here for them. Use the <Link href="/workbench" className="font-medium text-ink underline">Workbench</Link>.</div>;
  if (!data || !sum) return <p className="mt-6 flex items-center gap-2 text-sm text-slate-600"><Loader2 className="size-4 animate-spin" /> {err ?? "Loading"}</p>;

  const th = data.config.threshold_ms;
  const spikes = data.events.filter((e) => isSpike(e, th)).slice(-10).reverse();
  const tile = (label: string, value: string, note?: string, tone?: "signal") => (
    <div className="glass p-5 md:col-span-3">
      <div className="text-xs text-slate-600">{label}</div>
      <div className={tone === "signal" ? "mt-1 flex items-center gap-2 font-mono text-3xl font-semibold text-signal" : "mt-1 font-mono text-3xl font-semibold text-ink"}>
        {tone === "signal" && <Triangle className="size-5 fill-current" aria-hidden />}{value}
      </div>
      {note && <div className="text-xs text-slate-600">{note}</div>}
    </div>
  );
  const last = data.events.at(-1);
  return (
    <Bento className="mt-6">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700 md:col-span-12">
        <span className="inline-flex items-center gap-2 pill bg-ink px-3 py-1 text-xs font-medium text-white"><span className="size-2 animate-pulse rounded-full bg-lime" /> Live</span>
        updates every {n(data.config.poll_ms / 1000)} s; last {data.config.window_minutes} min
        {last && <span className="text-slate-500">last run {Math.max(0, Math.round((data.now - last.t) / 1000))} s ago by {last.user}</span>}
      </div>
      {tile("runs in the window", sum.runs.toLocaleString("en-US"), `${sum.perMinute} in the last minute`)}
      {tile("spikes", String(sum.spikes), `runs at or over ${th} ms`, "signal")}
      {tile("median", sum.p50 === null ? "none" : `${n(sum.p50)} ms`)}
      {tile("95th percentile", sum.p95 === null ? "none" : `${n(sum.p95)} ms`)}
      <figure className="glass min-w-0 p-5 md:col-span-12">
        <figcaption className="mb-2 text-base font-semibold text-slate-900">Query time while handling queries</figcaption>
        {data.events.length ? <Timeline events={data.events} threshold={th} from={Math.min(data.events[0].t, data.now - 60_000)} to={data.now} />
          : <p className="py-10 text-center text-sm text-slate-600">No queries yet. Sign in as an analyst in another window (or at 127.0.0.1 instead of localhost) and run some from the Workbench.</p>}
        <Source>every workbench run by any user, time measured by the gateway around the query (connection included); spike = at or over config.yaml workload.slow_query_ms</Source>
      </figure>
      <section className="glass min-w-0 p-5 md:col-span-7">
        <h3 className="mb-2 text-base font-semibold text-slate-900">Latest spikes</h3>
        {spikes.length ? (
          <ul className="space-y-1.5 text-sm">
            {spikes.map((e, i) => (
              <li key={i} className="flex items-center gap-3">
                <Triangle className="size-3.5 shrink-0 fill-signal text-signal" aria-label="spike" />
                <span className="shrink-0 font-mono text-xs text-slate-500">{hms(e.t)}</span>
                <span className="min-w-0 flex-1 truncate text-slate-800" title={e.sql}>{e.label}</span>
                <span className="shrink-0 text-xs text-slate-600">{e.user}</span>
                <span className="shrink-0 font-mono text-xs font-semibold text-ink">{n(e.ms)} ms</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-slate-600">No spikes in this window.</p>}
        {sum.slowest && <p className="mt-3 text-xs text-slate-600">Slowest: {sum.slowest.label}, {n(sum.slowest.ms)} ms. <Link href="/alerts" className="font-medium text-ink underline">Send an alert</Link></p>}
      </section>
      <section className="glass min-w-0 p-5 md:col-span-5">
        <h3 className="mb-2 text-base font-semibold text-slate-900">By user</h3>
        <ul className="space-y-1.5 text-sm">
          {sum.byUser.map((u) => (
            <li key={u.user} className="flex gap-3">
              <span className="min-w-0 flex-1 truncate text-slate-800">{u.user}</span>
              <span className="font-mono text-xs text-slate-600">{u.runs} runs</span>
              <span className="font-mono text-xs font-semibold text-signal">{u.spikes} spikes</span>
            </li>
          ))}
          {!sum.byUser.length && <li className="text-slate-600">Nobody has run a query yet.</li>}
        </ul>
      </section>
    </Bento>
  );
}
