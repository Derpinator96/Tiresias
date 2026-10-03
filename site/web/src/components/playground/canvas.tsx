"use client";
import { useEffect } from "react";
import {
  Background, BackgroundVariant, BaseEdge, Controls, Handle, Position, ReactFlow, ReactFlowProvider,
  getSmoothStepPath, useReactFlow, useStore, type Edge, type EdgeProps, type Node, type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity, Check, ClipboardCheck, Cpu, Database, FlaskConical, Grid3x3, Maximize, MessageSquareCode,
  PanelRight, Pause, Pickaxe, Play, RotateCcw, ShieldCheck, SkipBack, SkipForward,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { CONFIG } from "@/lib/facts";
import type { RunView } from "@/lib/run-view";
import { useView } from "@/lib/view";
import { RunBanner } from "@/components/viz/run-banner";
import { STAGES, stageState, useRun, type StageId } from "@/lib/store";
import { Pip } from "./bits";

const ICON: Record<StageId, typeof Database> = {
  source: Database, gateway: ShieldCheck, miner: Pickaxe, gnn: Cpu, rl: Grid3x3, llm: MessageSquareCode, twin: FlaskConical, dba: ClipboardCheck,
};

// Card body per stage: [label, value] pairs from the run view, plus a source line.
const n = (x: number | null, unit = " ms") => (x === null ? "not in bundle" : `${x.toFixed(1)}${unit}`);
const body = (v: RunView): Record<StageId, { rows: [string, string][]; note: string }> => ({
  source: { rows: [["mean before", n(v.meanBefore)], ["table rows", v.heroRows === null ? "not in bundle" : v.heroRows.toLocaleString("en-US")], ["slow threshold", `${v.slowThresholdMs} ms`]], note: v.src.prod },
  gateway: { rows: [["payloads scanned", String(v.payloads)], ["canary hits", `${v.canaryHits} of ${v.canariesPlanted}`], ["names", "HMAC-SHA256"]], note: v.src.ledger },
  miner: { rows: [["recommended", v.indexCols], ["columns", String(v.recommendedColumns)]], note: v.live ? `${v.candidates.length} candidates mined; FP-Growth, weighted by calls x latency` : "illustrative codes; FP-Growth, weighted by calls x latency; candidate count not in run record" },
  gnn: { rows: [["predicted before", n(v.predictedBefore)], ["predicted after", n(v.predictedAfter)]], note: v.estimatorLabel },
  rl: { rows: [["method", "tabular Q-learning"], ["actions", v.live ? String(v.actions.length) : `${CONFIG.episodes} episodes (config.yaml)`]], note: v.searchLabel },
  llm: { rows: [["model", v.llm.model], ["tool calls", v.llm.toolCalls === null ? "not in bundle" : String(v.llm.toolCalls)], v.live ? ["checker", v.llm.checker ?? "not run"] : ["numbers checked", String(v.llm.numbersChecked)]], note: v.live ? `${v.events.length} events, ${v.canaryHits} canary hits` : `${v.llmPayloads} payloads to the LLM, ${v.canaryHits} canary hits` },
  twin: { rows: [["before / after", `${n(v.twinBefore)} / ${n(v.twinAfter)}`], ["faster", v.speedupPct === null ? "not in bundle" : `${v.speedupPct.toFixed(1)}%`], ["storage", n(v.storageMb, " MB")]], note: v.src.twin },
  dba: { rows: [["migration.sql", v.migration ? "CREATE INDEX CONCURRENTLY" : "none"], ["rollback.sql", v.rollback ? "DROP INDEX CONCURRENTLY" : "none"]], note: "the DBA runs the files; nothing runs on pg-prod by itself" },
});

type StageData = { i: number; tgt: Position; src: Position };

function StageNode({ data, id }: NodeProps<Node<StageData>>) {
  const { step, status, completedAt, selected, gates } = useRun();
  const state = stageState(data.i, step, status);
  const v = useView();
  const Icon = ICON[id as StageId];
  const b = body(v)[id as StageId];
  return (
    <div className="stage-card w-[260px] p-3" data-state={state} data-selected={selected === id}>
      <Handle type="target" position={data.tgt} className="!size-2 !border-slate-300 !bg-white" />
      <div className="mb-2 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-md border border-slate-200/80 bg-slate-50 text-slate-700">
          {state === "processing" ? <Activity className="size-4 animate-pulse text-blue-600" /> : <Icon className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-wide text-slate-400">Stage {data.i + 1}</div>
          <div className="truncate text-sm font-semibold text-slate-900">{STAGES[data.i].title}</div>
        </div>
        {state === "done" ? (
          <span className="grid size-5 place-items-center rounded-full bg-emerald-500 text-white"><Check className="size-3" /></span>
        ) : (
          <Pip tone={state === "processing" ? "busy" : "idle"} />
        )}
      </div>
      {id === "gnn" && (
        <div className="mb-2 rounded-md border border-amber-300/70 bg-amber-50/80 px-2 py-1 font-mono text-[10.5px] leading-tight text-amber-900">
          {v.estimatorLabel}
        </div>
      )}
      <dl className="space-y-0.5">
        {b.rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 text-xs">
            <dt className="text-slate-500">{k}</dt>
            <dd className="truncate font-mono tracking-tight text-slate-800">{v}</dd>
          </div>
        ))}
        {id === "dba" && (
          <div className="flex justify-between gap-2 text-xs">
            <dt className="text-slate-500">pre-flight gates</dt>
            <dd className="font-mono text-slate-800">{gates.filter(Boolean).length} of 4</dd>
          </div>
        )}
      </dl>
      {id !== "gnn" && <p className="mt-1.5 line-clamp-2 text-[10.5px] leading-snug text-slate-500">{b.note}</p>}
      <div className="mt-1.5 h-4 text-[10.5px] text-emerald-700">{completedAt[data.i] && `replayed ${completedAt[data.i]}`}</div>
      <Handle type="source" position={data.src} className="!size-2 !border-slate-300 !bg-white" />
    </div>
  );
}

function ZoneNode({ data }: NodeProps<Node<{ label: string; sub: string; w: number; h: number; ai?: boolean }>>) {
  return (
    <div
      style={{ width: data.w, height: data.h }}
      className={cn("rounded-2xl border border-dashed p-3", data.ai ? "border-blue-300/80 bg-blue-50/30" : "border-slate-300/80 bg-white/20")}
    >
      <div className="text-xs font-semibold text-slate-700">{data.label}</div>
      <div className="text-[11px] text-slate-500">{data.sub}</div>
    </div>
  );
}

function FlowEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<Edge<{ i: number }>>) {
  const { step, status } = useRun();
  const i = data!.i; // edge from stage i to stage i + 1
  const active = step === i + 1 && status === "running";
  const done = step > i + 1;
  const [path] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 12 });
  return (
    <>
      <BaseEdge path={path} style={{ stroke: active ? "#2563EB" : done ? "#10B981" : "#CBD5E1", strokeWidth: active ? 2.5 : 1.75 }} />
      {active &&
        [0, 0.4].map((delay) => (
          <circle key={delay} r={4} fill="#2563EB">
            <animateMotion dur="0.8s" begin={`${delay}s`} repeatCount="indefinite" path={path} />
          </circle>
        ))}
    </>
  );
}

const X = [0, 330, 720, 1050];
const Y = [60, 400];
const POS: Record<StageId, [number, number, Position, Position]> = {
  source: [X[0], Y[0], Position.Left, Position.Right],
  gateway: [X[1], Y[0], Position.Left, Position.Right],
  miner: [X[2], Y[0], Position.Left, Position.Right],
  gnn: [X[3], Y[0], Position.Left, Position.Bottom],
  rl: [X[3], Y[1], Position.Top, Position.Left],
  llm: [X[2], Y[1], Position.Right, Position.Left],
  twin: [X[1], Y[1], Position.Right, Position.Left],
  dba: [X[0], Y[1], Position.Right, Position.Left],
};

const NODES: Node[] = [
  { id: "zone-private", type: "zone", position: { x: -30, y: 0 }, zIndex: -1, selectable: false, draggable: false, data: { label: "Private network", sub: "pg-prod, pg-twin, gateway: real names stay here", w: 650, h: 680 } },
  { id: "zone-ai", type: "zone", position: { x: 690, y: 0 }, zIndex: -1, selectable: false, draggable: false, data: { label: "AI zone", sub: "sees hashed names, ? for values, bitmasked roles only", w: 650, h: 680, ai: true } },
  ...STAGES.map((s, i) => {
    const [x, y, tgt, src] = POS[s.id];
    return { id: s.id, type: "stage", position: { x, y }, data: { i, tgt, src } };
  }),
];
const EDGES: Edge[] = STAGES.slice(1).map((s, i) => ({ id: `e${i}`, source: STAGES[i].id, target: s.id, type: "flow", data: { i } }));

function Toolbar() {
  const { step, status, speed, play, pause, forward, back, reset, setSpeed, toggleDrawer, drawerOpen } = useRun();
  const zoom = useStore((s) => s.transform[2]);
  const { fitView } = useReactFlow();
  const v = useView();

  useEffect(() => {
    if (status !== "running") return;
    const t = setInterval(forward, 1200 / speed); // replay pacing only, not a measured time
    return () => clearInterval(t);
  }, [status, speed, forward]);

  const btn = "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-900/5 disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <div className="glass-bar pointer-events-auto absolute left-1/2 top-3 z-20 flex w-[min(1180px,calc(100%-24px))] -translate-x-1/2 flex-wrap items-center gap-3 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="rounded-md border border-slate-200 bg-white/60 px-1.5 py-0.5 text-[11px] text-slate-600">{v.live ? "asked question" : "demo retail DB, 10M rows"}</span>
        <span className="font-mono text-[11px] text-slate-500">{v.id}</span>
      </div>
      <div className="mx-auto flex flex-wrap items-center gap-1">
        {status === "running" ? (
          <button className={cn(btn, "bg-slate-900 text-white hover:bg-slate-800")} onClick={pause}><Pause className="size-3.5" /> Pause</button>
        ) : (
          <button className={cn(btn, "bg-slate-900 text-white hover:bg-slate-800")} onClick={play}>
            <Play className="size-3.5" /> {status === "completed" ? "Replay again" : step > 0 ? "Resume" : "Run pipeline"}
          </button>
        )}
        <button className={btn} onClick={back} disabled={step === 0} title="Step back"><SkipBack className="size-3.5" /> Back</button>
        <button className={btn} onClick={forward} disabled={step === STAGES.length} title="Step forward"><SkipForward className="size-3.5" /> Forward</button>
        <button className={btn} onClick={reset} disabled={step === 0 && status === "idle"} title="Reset"><RotateCcw className="size-3.5" /> Reset</button>
        <div className="ml-1 flex rounded-md border border-slate-200 bg-white/70 p-0.5" role="group" aria-label="Playback speed">
          {([1, 2, 5] as const).map((s) => (
            <button key={s} onClick={() => setSpeed(s)} aria-pressed={speed === s}
              className={cn("h-6 rounded px-2 font-mono text-[11px]", speed === s ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>
              {s}x
            </button>
          ))}
        </div>
        <span className="ml-2 flex items-center gap-1.5 whitespace-nowrap text-xs text-slate-600">
          <Pip tone={status === "running" ? "busy" : status === "completed" ? "ok" : "idle"} />
          {status} · {step} of {STAGES.length}
        </span>
      </div>
      <div className="flex items-center gap-1">
        <span className="flex items-center gap-1.5 text-[11px] text-slate-500" title="Where the figures come from">
          <Pip tone={v.live ? "ok" : "idle"} /> {v.live ? "bundle" : "run record"}
        </span>
        <span className="ml-1 rounded-md border border-slate-200 bg-white/70 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">{Math.round(zoom * 100)}%</span>
        <button className={btn} onClick={() => fitView({ padding: 0.12, duration: 300 })}><Maximize className="size-3.5" /> Fit</button>
        <button className={cn(btn, drawerOpen && "bg-slate-900/5")} onClick={toggleDrawer} aria-pressed={drawerOpen}><PanelRight className="size-3.5" /> Inspector</button>
      </div>
      <div className="absolute inset-x-3 bottom-0 h-0.5 overflow-hidden rounded bg-slate-200/70">
        <div className="h-full bg-blue-600 transition-[width] duration-300" style={{ width: `${(step / STAGES.length) * 100}%` }} />
      </div>
    </div>
  );
}

function EventLog() {
  const log = useRun((s) => s.log);
  const v = useView();
  return (
    <div className="glass pointer-events-auto absolute bottom-3 left-14 z-10 w-[min(340px,calc(100%-68px))] rounded-xl p-3">
      <div className="mb-1 text-xs font-semibold text-slate-900">Replay log</div>
      <p className="mb-2 text-[11px] leading-snug text-slate-500">{v.id}: figures from the {v.live ? "bundle" : "run record"}; pacing is not real timing</p>
      <ol className="max-h-32 space-y-0.5 overflow-y-auto font-mono text-[11px] text-slate-700">
        {log.length === 0 && <li className="text-slate-400">no events yet: press Run pipeline or Forward</li>}
        {[...log].reverse().map((e, i) => (
          <li key={log.length - i}><span className="text-slate-400">{e.t}</span> {e.msg}</li>
        ))}
      </ol>
    </div>
  );
}

const nodeTypes = { stage: StageNode, zone: ZoneNode };
const edgeTypes = { flow: FlowEdge };

function Flow() {
  const select = useRun((s) => s.select);
  return (
    <ReactFlow
      defaultNodes={NODES}
      defaultEdges={EDGES}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView
      fitViewOptions={{ padding: 0.12 }}
      minZoom={0.3}
      maxZoom={2}
      nodesConnectable={false}
      onNodeClick={(_, n) => n.type === "stage" && select(n.id as StageId)}
      onPaneClick={() => select(null)}
      attributionPosition="bottom-right"
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#94A3B8" />
      <Controls position="bottom-left" className="!rounded-lg !border !border-white/70 !shadow-[0_14px_34px_rgba(15,23,42,0.08)]" />
    </ReactFlow>
  );
}

export function Canvas({ children }: { children?: React.ReactNode }) {
  const v = useView();
  const setSource = useRun((s) => s.setSource);
  useEffect(() => setSource(v.id), [v.id, setSource]);
  return (
    <ReactFlowProvider>
      <div className="flex h-[calc(100dvh-3rem)] w-full flex-col overflow-hidden lg:h-dvh">
        <h1 className="sr-only">Tiresias pipeline replay of {v.id}</h1>
        <RunBanner className="m-2 mb-0 shrink-0" />
        <div className="relative min-h-0 flex-1">
          <Flow />
          <Toolbar />
          <EventLog />
          {children}
        </div>
      </div>
    </ReactFlowProvider>
  );
}
