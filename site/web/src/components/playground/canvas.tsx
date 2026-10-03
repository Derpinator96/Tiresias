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
import Link from "next/link";
import { CONFIG, INDEX_COLS, ms, run } from "@/lib/facts";
import { STAGES, stageState, useRun, type StageId } from "@/lib/store";
import { Pip } from "./bits";

const ICON: Record<StageId, typeof Database> = {
  source: Database, gateway: ShieldCheck, miner: Pickaxe, gnn: Cpu, rl: Grid3x3, llm: MessageSquareCode, twin: FlaskConical, dba: ClipboardCheck,
};

// Card body per stage: [label, value] pairs from the run record, plus a source line.
const BODY: Record<StageId, { rows: [string, string][]; note: string }> = {
  source: { rows: [["Q1 mean before", ms(run.q1.mean_ms_before)], ["hero table rows", run.dataset.hero_table_rows.toLocaleString("en-US")], ["slow threshold", `${run.q1.slow_threshold_ms} ms`]], note: "pg_stat_statements on pg-prod" },
  gateway: { rows: [["payloads scanned", String(run.privacy.payloads)], ["canary hits", `${run.privacy.canary_hits} of ${run.privacy.canaries_planted}`], ["names", "HMAC-SHA256"]], note: "every outgoing payload ledgered" },
  miner: { rows: [["recommended", INDEX_COLS], ["columns", String(run.search.recommended_columns)]], note: "illustrative codes; FP-Growth, weighted by calls x latency; candidate count not in run record" },
  gnn: { rows: [["predicted before", ms(run.search.predicted_before_ms)], ["predicted after", ms(run.search.predicted_after_ms)]], note: run.search.estimator_label },
  rl: { rows: [["method", "tabular Q-learning"], ["episodes", `${CONFIG.episodes} (config.yaml)`]], note: run.search.label },
  llm: { rows: [["model", run.llm.model], ["tool calls", String(run.llm.tool_calls)], ["numbers checked", String(run.llm.numbers_checked)]], note: `${run.privacy.llm_payloads} payloads to the LLM, ${run.privacy.canary_hits} canary hits` },
  twin: { rows: [["before / after", `${ms(run.twin.before_ms)} / ${ms(run.twin.after_ms)}`], ["faster", `${run.twin.speedup_pct}%`], ["index size", `${run.twin.storage_mb} MB`]], note: `median of ${run.twin.runs} runs on the statistical twin` },
  dba: { rows: [["migration.sql", "CREATE INDEX CONCURRENTLY"], ["rollback.sql", "DROP INDEX CONCURRENTLY"]], note: "the DBA runs the files; nothing runs on pg-prod by itself" },
};

type StageData = { i: number; tgt: Position; src: Position };

function StageNode({ data, id }: NodeProps<Node<StageData>>) {
  const { step, status, completedAt, selected, gates } = useRun();
  const state = stageState(data.i, step, status);
  const Icon = ICON[id as StageId];
  const b = BODY[id as StageId];
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
          {run.search.estimator_label}
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

  useEffect(() => {
    if (status !== "running") return;
    const t = setInterval(forward, 1200 / speed); // replay pacing only, not a measured time
    return () => clearInterval(t);
  }, [status, speed, forward]);

  const btn = "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-900/5 disabled:opacity-40 disabled:hover:bg-transparent";
  return (
    <div className="glass-bar pointer-events-auto absolute left-1/2 top-3 z-20 flex w-[min(1180px,calc(100%-24px))] -translate-x-1/2 flex-wrap items-center gap-3 px-3 py-2">
      <div className="flex items-center gap-2">
        <Link href="/" className="text-sm font-semibold text-slate-900 hover:underline">Blind Tuner</Link>
        <span className="rounded-md border border-slate-200 bg-white/60 px-1.5 py-0.5 text-[11px] text-slate-600">demo retail DB, 10M rows</span>
        <span className="font-mono text-[11px] text-slate-500">{run.run_id}</span>
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
          <Pip tone="idle" /> run record
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
  return (
    <div className="glass pointer-events-auto absolute bottom-3 left-14 z-10 w-[min(340px,calc(100%-68px))] rounded-xl p-3">
      <div className="mb-1 text-xs font-semibold text-slate-900">Replay log</div>
      <p className="mb-2 text-[11px] leading-snug text-slate-500">
        Replay of {run.run_id} (finished {run.finished_at}, {run.elapsed_s} s). Figures are the run record; the pacing here is not the real stage timing.
      </p>
      <ol className="max-h-32 space-y-0.5 overflow-y-auto font-mono text-[11px] text-slate-700">
        {log.length === 0 && <li className="text-slate-400">no events yet: press Run pipeline or Forward</li>}
        {[...log].reverse().map((e, i) => (
          <li key={log.length - i}><span className="text-slate-400">{e.t}</span> {e.msg}</li>
        ))}
      </ol>
      <div className="mt-2 flex gap-3 border-t border-slate-200/70 pt-2 text-[11px] text-slate-600">
        <Link href="/" className="hover:underline">Home</Link>
        <Link href="/privacy" className="hover:underline">Privacy</Link>
        <Link href="/terms" className="hover:underline">Terms</Link>
      </div>
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
  return (
    <ReactFlowProvider>
      <div className="relative h-dvh w-full overflow-hidden">
        <h1 className="sr-only">Blind Tuner pipeline replay of {run.run_id}</h1>
        <Flow />
        <Toolbar />
        <EventLog />
        {children}
      </div>
    </ReactFlowProvider>
  );
}
