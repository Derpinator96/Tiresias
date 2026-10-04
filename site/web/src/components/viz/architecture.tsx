"use client";
// The overview centrepiece: the 8 stages in their 3 trust zones, SVG edges in the same pixel
// coordinates as the HTML node cards (the container is measured with a ResizeObserver, so the
// edges and packets never stretch). Packets: while a question runs (context store `running`), fast
// lime dots on the edges into the current stage; idle, one slow packet loops over the whole path.
// Layout constants live here (this file is not scanned by tests/spans.test.mjs); every figure on a
// node comes from useView().
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, Lock } from "lucide-react";
import { useCountUp } from "@/components/viz/charts";
import { CONFIG } from "@/lib/facts";
import { useContextStore } from "@/lib/context";
import { toolOf } from "@/lib/progress";
import type { RunView } from "@/lib/run-view";
import { STAGES, STAGE_COPY, STAGE_ICON, STAGE_SUMMARY, STAGE_TINT, type StageId } from "@/lib/stages";
import { useView } from "@/lib/view";
import { cn } from "@/lib/utils";

const H = 420;            // diagram height in px
const NODE_W = 176;       // node card width in px
const LIME = "#f0ff97", INK = "#262726";

// Node centres as fractions of the container (x) and of H (y).
const POS: Record<StageId, [number, number]> = {
  source: [0.11, 0.3], gateway: [0.11, 0.72],
  miner: [0.335, 0.3], gnn: [0.5, 0.3], rl: [0.665, 0.3], llm: [0.5, 0.72],
  twin: [0.89, 0.3], dba: [0.89, 0.72],
};
// Main data flow, then the gateway's metadata links to each AI node.
const FLOW: [StageId, StageId][] = [["source", "gateway"], ["gateway", "miner"], ["miner", "gnn"], ["gnn", "rl"], ["rl", "twin"], ["twin", "llm"], ["llm", "dba"]];
const META: StageId[] = ["miner", "gnn", "rl", "llm"];
const ZONES = [
  { x0: 0, x1: 0.22, label: "Private network", sub: "real names stay here", cls: "bg-leaf/60 text-ink" },
  { x0: 0.25, x1: 0.75, label: "AI zone", sub: "hashed codes, ? for values", cls: "bg-ink text-white" },
  { x0: 0.78, x1: 1, label: "Private network", sub: "measured, then approved", cls: "bg-sky/60 text-ink" },
];
const BOUNDARIES = [0.235, 0.765];

const title = (id: StageId) => STAGES.find((s) => s.id === id)!.title;

function curve(w: number, a: StageId, b: StageId) {
  const [x1, y1] = [POS[a][0] * w, POS[a][1] * H], [x2, y2] = [POS[b][0] * w, POS[b][1] * H];
  if (Math.abs(x1 - x2) < 1) return `M${x1} ${y1} L${x2} ${y2}`;
  const mx = (x1 + x2) / 2;
  return `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`;
}

/** A number that counts up to its new value when a fresh result arrives. */
function N({ value, digits = 0 }: { value: number; digits?: number }) {
  const v = useCountUp(value);
  return <>{v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}</>;
}

function Figure({ id, v }: { id: StageId; v: RunView }) {
  switch (id) {
    case "source": return v.heroRows === null ? <>rows not in bundle</> : <><N value={v.heroRows} /> rows</>;
    case "gateway": return <><N value={v.payloads} /> payloads, <N value={v.canaryHits} /> hits</>;
    case "miner": return v.live ? <><N value={v.candidates.length} /> candidates</> : <><N value={v.recommendedColumns} />-column index</>;
    case "gnn": return <span title={v.estimatorLabel}>{v.estimatorLabel.replace(/^estimator:\s*/, "")}</span>;
    case "rl": return v.live ? <><N value={v.actions.length} /> actions chosen</> : <><N value={CONFIG.episodes} /> episodes (config)</>;
    case "llm": return <span title={v.llm.model}>{v.llm.toolCalls === null ? "" : <><N value={v.llm.toolCalls} /> tools, </>}{v.llm.model}</span>;
    case "twin": return v.speedupPct === null ? <>no twin result</> : <><N value={v.speedupPct} digits={1} />% faster</>;
    case "dba": return <>{v.migration ? "SQL ready" : "no SQL"}</>;
  }
}

function Node({ id, w, v, state }: { id: StageId; w: number; v: RunView; state: "idle" | "active" | "done" }) {
  const Icon = STAGE_ICON[id];
  const c = STAGE_COPY[id];
  const [fx, fy] = POS[id];
  const ai = META.includes(id);
  const below = fy < 0.5; // hover card opens away from the edge
  return (
    <div className="group/node absolute z-10" style={{ left: fx * w - NODE_W / 2, top: fy * H - 34, width: NODE_W }}>
      <Link href={`/stages/${id}`} aria-label={title(id)}
        className={cn("relative flex min-h-[68px] items-center gap-2.5 rounded-2xl p-2.5 shadow-(--glass-shadow) transition-transform hover:-translate-y-0.5 motion-reduce:transition-none",
          ai ? "bg-white/10 text-white backdrop-blur-xl" : "bg-white text-ink", state === "active" && "ring-2 ring-lime")}>
        {state === "active" && <span className="absolute -inset-1 animate-pulse rounded-[1.1rem] ring-4 ring-lime/50 motion-reduce:animate-none" aria-hidden />}
        <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl text-ink", STAGE_TINT[id].bg)}><Icon className="size-4" /></span>
        <span className="min-w-0">
          <span className="block truncate text-xs font-semibold">{title(id)}</span>
          <span className={cn("line-clamp-2 font-mono text-xs leading-tight", ai ? "text-white/70" : "text-slate-600")}><Figure id={id} v={v} /></span>
        </span>
        {state === "done" && <span className="absolute -right-1.5 -top-1.5 grid size-5 place-items-center rounded-full bg-ink text-white ring-2 ring-white" aria-label="reached"><Check className="size-3" /></span>}
      </Link>
      <div className={cn("invisible absolute left-1/2 z-30 w-64 -translate-x-1/2 rounded-2xl bg-white p-3 text-xs text-slate-700 opacity-0 shadow-(--glass-shadow-lg) transition-opacity group-focus-within/node:visible group-focus-within/node:opacity-100 group-hover/node:visible group-hover/node:opacity-100 motion-reduce:transition-none",
        below ? "top-full mt-2" : "bottom-full mb-2")}>
        <div className="mb-1 font-semibold text-ink">{title(id)}</div>
        <p>{STAGE_SUMMARY[id]}</p>
        {c.sent && <><div className="mt-2 font-medium text-ink">Sent</div><ul className="list-inside list-disc">{c.sent.map((x) => <li key={x}>{x}</li>)}</ul></>}
        {c.never && <><div className="mt-2 font-medium text-ink">Never sent</div><ul className="list-inside list-disc">{c.never.map((x) => <li key={x}>{x}</li>)}</ul></>}
        <Link href={`/stages/${id}`} className="mt-2 inline-flex items-center gap-1 font-medium text-ink hover:underline">Open the stage page <ArrowRight className="size-3" /></Link>
      </div>
    </div>
  );
}

function Packets({ d, dur, n }: { d: string; dur: number; n: number }) {
  return <>{Array.from({ length: n }, (_, i) => (
    <circle key={`${d}-${i}`} r={4} fill={LIME} stroke={INK} strokeWidth={1}>
      <animateMotion dur={`${dur}s`} begin={`${(i * dur) / n}s`} repeatCount="indefinite" path={d} />
    </circle>
  ))}</>;
}

const ago = (ms: number) => (ms < 60000 ? `${Math.max(0, Math.round(ms / 1000))} s ago` : `${Math.round(ms / 60000)} min ago`);
const short = (e: string) => { const t = toolOf(e); return t ? `tool ${t}` : e.length > 48 ? `${e.slice(0, 47)}...` : e; };

/** Latest 5 events: the running question's (with when each first arrived here), else the bundle's. */
function Ticker({ v }: { v: RunView }) {
  const running = useContextStore((s) => s.running);
  // first time each live event was seen here (the events carry no timestamps); sampled every 500 ms
  const [seen, setSeen] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => {
      const r = useContextStore.getState().running, t0 = Date.now();
      setNow(t0);
      if (r) setSeen((s) => { const fresh = r.events.map((_, i) => `${r.qid}:${i}`).filter((k) => !(k in s)); return fresh.length ? { ...s, ...Object.fromEntries(fresh.map((k) => [k, t0])) } : s; });
    }, 500);
    return () => clearInterval(t);
  }, []);
  const events = running ? running.events : v.events;
  const key = (i: number) => `${running?.qid ?? v.id}:${i}`;
  const last = events.map((e, i) => ({ e, i })).slice(-5).reverse();
  return (
    <div className="mt-3 flex items-center gap-1.5 overflow-hidden text-xs *:shrink-0">
      <span className="max-w-[18rem] truncate text-slate-500">{running ? `Live: ${running.question}` : v.live ? `Events of bundle ${v.id}` : "No question asked yet: the run record has no event log"}</span>
      {running && !events.length && <span className="pill bg-white px-2.5 py-1 text-slate-600 shadow-(--glass-shadow)">question received, waiting for the first tool call</span>}
      {last.map(({ e, i }) => (
        <span key={key(i)} className="pill bg-white px-2.5 py-1 font-mono text-slate-700 shadow-(--glass-shadow)" title={e}>
          {short(e)}{running && key(i) in seen && <span className="ml-1.5 text-slate-400">{ago(now - seen[key(i)])}</span>}
        </span>
      ))}
    </div>
  );
}

export function Architecture() {
  const v = useView();
  const running = useContextStore((s) => s.running);
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Test hook for driving a live run from the console; development builds only.
  useEffect(() => {
    if (process.env.NODE_ENV === "development") (window as unknown as { __btStart?: unknown }).__btStart = useContextStore.getState().start;
  }, []);

  const stage = running?.stage ?? null;
  const reached = new Set(running?.reached ?? []);
  const state = (id: StageId) => (id === stage ? "active" : reached.has(id) ? "done" : "idle");
  const hot = (a: StageId, b: StageId) => !!stage && b === stage && a !== b;
  const ambient = w ? FLOW.map(([a, b]) => curve(w, a, b)).join(" ") : "";

  return (
    <div>
      <div ref={box} className="relative w-full" style={{ height: H }}>
        {w > 0 && <>
          {ZONES.map((z) => (
            <div key={z.x0} className={cn("absolute inset-y-0 rounded-3xl p-4", z.cls)} style={{ left: z.x0 * w, width: (z.x1 - z.x0) * w }}>
              <div className="text-sm font-semibold">{z.label}</div>
              <div className="text-xs opacity-70">{z.sub}</div>
            </div>
          ))}
          <svg className="pointer-events-none absolute inset-0" width={w} height={H} viewBox={`0 0 ${w} ${H}`} aria-hidden>
            {BOUNDARIES.map((b) => <line key={b} x1={b * w} x2={b * w} y1={12} y2={H - 12} stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 5" />)}
            {META.map((m) => <path key={m} d={curve(w, "gateway", m)} fill="none" stroke={hot("gateway", m) ? LIME : "#94a3b8"} strokeWidth={1} strokeDasharray="2 4" opacity={0.7} />)}
            {FLOW.map(([a, b]) => <path key={a + b} d={curve(w, a, b)} fill="none" stroke={hot(a, b) ? LIME : "#94a3b8"} strokeWidth={hot(a, b) ? 3 : 1.75} />)}
            {running
              ? <>
                  {FLOW.filter(([a, b]) => hot(a, b)).map(([a, b]) => <Packets key={a + b} d={curve(w, a, b)} dur={0.9} n={3} />)}
                  {META.filter((m) => hot("gateway", m)).map((m) => <Packets key={m} d={curve(w, "gateway", m)} dur={1.1} n={2} />)}
                </>
              : <Packets d={ambient} dur={16} n={1} />}
          </svg>
          {BOUNDARIES.map((b) => (
            <div key={b} className="absolute z-20 flex -translate-x-1/2 items-center gap-1 rounded-full bg-white px-2 py-1 text-xs text-slate-700 shadow-(--glass-shadow)" style={{ left: b * w, top: H / 2 - 14 }}>
              <Lock className="size-3" aria-hidden /> only hashed codes cross
            </div>
          ))}
          {STAGES.map((s) => <Node key={s.id} id={s.id} w={w} v={v} state={state(s.id)} />)}
        </>}
      </div>
      <Ticker v={v} />
    </div>
  );
}
