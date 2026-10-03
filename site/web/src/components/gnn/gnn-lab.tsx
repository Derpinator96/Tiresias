"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Pause, Play, TriangleAlert } from "lucide-react";
import { BigNumber, ChartCard, HBars, SERIES } from "@/components/viz/charts";
import { layout, misestimate, numericFeatures, opIndex, planOptions, predictedShares, reach, serves, shares, type PlanNode } from "@/lib/gnn";
import { name, useBundle } from "@/lib/context";
import type { Bundle, Explain, Prediction } from "@/lib/bundle";
import { run } from "@/lib/facts";
import plans from "@/data/gnn_plans.json";
import spec from "@/data/gnn_spec.json";
import m from "@/data/measurements.json";
import { cn } from "@/lib/utils";

const seg = (on: boolean) => cn("h-7 whitespace-nowrap rounded px-2.5 text-xs", on ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70");
const Seg = ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={cn("glass-subtle flex w-fit flex-wrap rounded-md p-0.5", className)}>{children}</div>;
const nFeatures = spec.ops.length + spec.numeric.length;

// Tree geometry in pixels: layout() gives x in leaf units and y in depth levels.
// Boxes hold two 13px lines (20px line height each) plus padding; the tooltip rows are 20px.
const BOX_W = 168, BOX_H = 64, COL = 192, ROW = 112, PAD = 12, TIP_W = 224, TIP_ROW = 20;
// SVG strokes: slate-300, accent, ink (CSS classes cannot colour an SVG marker here)
const EDGE = { idle: "rgb(203 213 225)", reach: SERIES.blue, hot: "rgb(15 23 42)" } as const;
const heat = (s: number) => `rgb(37 99 235 / ${(0.5 * s).toFixed(3)})`;   // accent at an alpha proportional to the share
const pct = (s: number) => `${(s * 100).toFixed(1)}%`;
const int = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

type Option = { id: string; label: string; nodes: PlanNode[]; prediction?: Prediction | null; explain?: Explain | null; hypopg?: PlanNode[] };

/** One plan per picker entry: the bundle's logged plans (plans[tid][0]) or the illustrative ones. */
function options(b: Bundle | null): Option[] {
  if (!b || !planOptions(b).length) return plans.plans.map((p) => ({ id: p.id, label: p.label, nodes: p.nodes as PlanNode[] }));
  const indexed = b.config?.actions.some((a) => a.type === "add_index");
  return planOptions(b).map(({ tid, label }) => ({
    id: tid, label, nodes: b.plans[tid][0].nodes, prediction: b.predictions[tid], explain: b.explain[tid],
    hypopg: indexed ? b.hypopg?.plans.find((p) => p.template_id === tid)?.nodes : undefined,
  }));
}

export function GnnLab() {
  const b = useBundle();
  // Keyed on the bundle: every selection resets when the asked question changes.
  return <Lab key={b?.id ?? "illustrative"} b={b} />;
}

function Lab({ b }: { b: Bundle | null }) {
  const opts = useMemo(() => options(b), [b]);
  const [planId, setPlanId] = useState(opts[0].id);
  const [variant, setVariant] = useState<"baseline" | "hypopg">("baseline");
  const [by, setBy] = useState<"cost" | "time" | "gnn">("cost");
  const [real, setReal] = useState(true);
  const [layers, setLayers] = useState(spec.layers);
  const [sel, setSel] = useState(0);
  const [hl, setHl] = useState<number | null>(null);   // hovered node id, from the tree or the explain bars
  const [playing, setPlaying] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);   // the hovered box on screen: the tooltip is fixed beside it
  const opt = opts.find((p) => p.id === planId) ?? opts[0];
  const nodes = variant === "hypopg" && opt.hypopg ? opt.hypopg : opt.nodes;
  const gnnMode = variant === "baseline" && !!opt.prediction;   // predictions exist for plans[tid][0] only
  const timed = nodes.some((n) => n.self_ms !== undefined);
  const mode = (by === "gnn" && !gnnMode) || (by === "time" && !timed) ? "cost" : by;
  const pos = useMemo(() => layout(nodes), [nodes]);
  const all = useMemo(() => ({
    cost: shares(nodes, "cost"), time: timed ? shares(nodes, "time") : null, gnn: gnnMode ? predictedShares(nodes, opt.prediction) : null,
  }), [nodes, timed, gnnMode, opt.prediction]);
  const share = all[mode] ?? all.cost;
  const feats = useMemo(() => numericFeatures(nodes), [nodes]);
  const seen = useMemo(() => reach(nodes, sel, layers), [nodes, sel, layers]);
  const node = nodes[sel] ?? nodes[0];
  const f = feats[sel] ?? feats[0];
  const ratio = node.actual_rows === undefined ? null : misestimate(node.est_rows, node.actual_rows);
  const label = (code: string | undefined) => (code ? (real ? name(b, code) : code) : "");
  const root = (ns: PlanNode[]) => ns.find((n) => n.parent_id === null)?.est_cost ?? 0;

  // Pixel positions: box centre x and box top y.
  const at = (id: number) => { const p = pos.find((q) => q.id === id)!; return { cx: PAD + p.x * COL + BOX_W / 2, top: PAD + p.y * ROW }; };
  const treeW = PAD * 2 + Math.max(...pos.map((p) => p.x)) * COL + BOX_W;
  const treeH = PAD * 2 + Math.max(...pos.map((p) => p.y)) * ROW + BOX_H;
  const hot = hl === null ? null : nodes.findIndex((n) => n.node_id === hl);
  const hover = (id: number) => { setAnchor(wrap.current?.querySelector(`[data-node="${id}"]`)?.getBoundingClientRect() ?? null); setHl(id); };

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setLayers((l) => (l >= spec.layers ? (setPlaying(false), l) : l + 1)), 900);
    return () => clearInterval(t);
  }, [playing]);

  const [gnn, setGnn] = useState(m.gnn.models[0].median);
  const [pg, setPg] = useState(m.gnn.models[2].median);
  const who = serves(gnn, pg);
  const pick = (id: string) => { setPlanId(id); setSel(0); setVariant("baseline"); };
  const explainMax = Math.max(...(opt.explain?.top_nodes.map((n) => n.predicted_share_pct) ?? [1]));

  return (
    <div className="space-y-4">
      <div className="glass flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl p-4">
        <Seg className="flex-wrap">{opts.map((p) => <button key={p.id} className={cn(seg(planId === p.id), "max-w-72 truncate font-mono")} title={b ? name(b, p.id) : undefined} onClick={() => pick(p.id)}>{p.label}</button>)}</Seg>
        {opt.hypopg && (
          <Seg>
            <button className={seg(variant === "baseline")} onClick={() => { setVariant("baseline"); setSel(0); }}>baseline plan</button>
            <button className={seg(variant === "hypopg")} onClick={() => { setVariant("hypopg"); setSel(0); }}>with the recommended index (HypoPG)</button>
          </Seg>
        )}
        <Seg>
          <button className={seg(mode === "cost")} onClick={() => setBy("cost")}>Postgres cost share</button>
          {timed && <button className={seg(mode === "time")} onClick={() => setBy("time")}>Measured time share</button>}
          {gnnMode && <button className={seg(mode === "gnn")} onClick={() => setBy("gnn")}>GNN predicted share</button>}
        </Seg>
        {b && (
          <Seg>
            <button className={seg(real)} onClick={() => setReal(true)}>real names</button>
            <button className={seg(!real)} onClick={() => setReal(false)}>what the AI sees</button>
          </Seg>
        )}
        <div className="ml-auto flex gap-8">
          <BigNumber value={String(spec.layers)} label="layers" />
          <BigNumber value={String(spec.hidden_size)} label="hidden size" />
          <BigNumber value={String(nFeatures)} label="features per node" />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <ChartCard title={variant === "hypopg" ? "Plan tree with the recommended index" : "Plan tree"} caption={b
          ? <>Logged auto_explain plan, newest first, bundle {b.id}.{mode === "gnn" ? ` Predicted share: ${b.estimator?.label ?? opt.prediction?.estimator}.` : ""}{variant === "hypopg" ? " HypoPG plan: EXPLAIN with a hypothetical index, no actual rows or times." : ""} Codes under &quot;what the AI sees&quot; are the gateway&apos;s HMAC codes.</>
          : <>Illustrative plans, not from {run.run_id}: {plans._source}</>}>
          <div ref={wrap} className="inset-field overflow-x-auto rounded-lg" onMouseLeave={() => setHl(null)}>
            <div className="relative mx-auto" style={{ width: treeW, height: treeH }}>
              <svg className="absolute inset-0" width={treeW} height={treeH} aria-hidden>
                <defs>
                  {Object.entries(EDGE).map(([k, c]) => (
                    <marker key={k} id={`gnn-arrow-${k}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                      <path d="M0,0.5 L8,4 L0,7.5 Z" fill={c} />
                    </marker>
                  ))}
                </defs>
                {nodes.filter((n) => n.parent_id !== null).map((n) => {
                  const p = at(n.parent_id!), c = at(n.node_id);
                  const y0 = p.top + BOX_H, y1 = c.top, mid = (y0 + y1) / 2;
                  const on = seen.has(n.node_id) && seen.has(n.parent_id!);
                  const isHot = hl !== null && (hl === n.node_id || hl === n.parent_id);
                  const tone = isHot ? "hot" : on ? "reach" : "idle";
                  return (
                    <path key={n.node_id} d={`M${p.cx},${y0} C${p.cx},${mid} ${c.cx},${mid} ${c.cx},${y1}`} fill="none" stroke={EDGE[tone]} strokeWidth={isHot ? 2.5 : on ? 2 : 1.5}
                      markerStart={`url(#gnn-arrow-${tone})`} strokeDasharray={on && layers > 0 ? "6 4" : undefined} className="transition-[stroke,stroke-width]">
                      {on && layers > 0 && <animate attributeName="stroke-dashoffset" from="20" to="0" dur="0.8s" repeatCount="indefinite" />}
                    </path>
                  );
                })}
              </svg>
              {nodes.map((n, i) => {
                const { cx, top } = at(n.node_id);
                const s = share[i];
                const isHot = hl === n.node_id;
                return (
                  <button key={n.node_id} onClick={() => setSel(i)} onMouseEnter={() => hover(n.node_id)} onMouseLeave={() => setHl(null)} onFocus={() => hover(n.node_id)} onBlur={() => setHl(null)} aria-pressed={sel === i} data-node={n.node_id}
                    className={cn("inset-field absolute overflow-hidden px-2 py-1.5 text-left shadow-sm transition-[transform,box-shadow,opacity,border-color] duration-150",
                      sel === i && "border-ink ring-2 ring-ink/30", isHot && "-translate-y-0.5 border-accent shadow-lg", !seen.has(n.node_id) && "opacity-40")}
                    style={{ left: cx - BOX_W / 2, top, width: BOX_W, height: BOX_H, backgroundColor: heat(s) }}>
                    <div className="truncate text-xs font-medium text-slate-900">{n.op}</div>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate font-mono text-xs text-slate-600" title={label(n.relation)}>{label(n.relation)}</span>
                      <span className="font-mono text-xs text-slate-800">{pct(s)}</span>
                    </div>
                  </button>
                );
              })}
              {hot !== null && hot >= 0 && anchor && (() => {
                const n = nodes[hot];
                const rows: [string, string][] = [
                  ["est rows", int(n.est_rows)], ["actual rows", n.actual_rows === undefined ? "n/a" : int(n.actual_rows)], ["est cost", int(n.est_cost)], ["width", String(n.width)],
                  ["self ms", n.self_ms === undefined ? "n/a" : n.self_ms.toFixed(2)], ["cost share", pct(all.cost[hot])],
                  ...(all.time ? [["time share", pct(all.time[hot])] as [string, string]] : []), ...(all.gnn ? [["GNN share", pct(all.gnn[hot])] as [string, string]] : []),
                ];
                // Fixed beside the hovered box (right when it fits, else left), kept inside the viewport. Portalled to
                // the body: the glass backdrop-filter would otherwise make the card the containing block.
                const tipH = 48 + rows.length * TIP_ROW;
                const left = anchor.right + 8 + TIP_W <= window.innerWidth ? anchor.right + 8 : Math.max(8, anchor.left - TIP_W - 8);
                const top = Math.max(8, Math.min(anchor.top, window.innerHeight - tipH - 8));
                return createPortal(
                  <div className="glass-strong pointer-events-none fixed z-10 rounded-md px-2.5 py-2 text-xs" style={{ left, top, width: TIP_W }}>
                    <div className="mb-1 font-medium text-slate-900">node {n.node_id}: {n.op}</div>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                      {rows.map(([k, v]) => <Fragment key={k}><dt className="text-slate-600">{k}</dt><dd className="text-right font-mono text-slate-900">{v}</dd></Fragment>)}
                    </dl>
                  </div>,
                  document.body,
                );
              })()}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="inline-flex h-7 items-center gap-1 rounded-md bg-slate-900 px-2 text-xs text-white hover:bg-slate-800" onClick={() => { if (layers >= spec.layers) setLayers(0); setPlaying(!playing); }}>
              {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} Message passing
            </button>
            <label className="flex min-w-40 flex-1 items-center gap-2 text-xs text-slate-700">
              layers
              <input type="range" min={0} max={spec.layers} step={1} value={layers} onChange={(e) => { setPlaying(false); setLayers(Number(e.target.value)); }} className="w-full accent-accent" />
              <span className="font-mono text-slate-900">{layers}</span>
            </label>
            <span className="text-xs text-slate-600">{seen.size} of {nodes.length} nodes reach node {node.node_id}</span>
          </div>
          {opt.hypopg && (
            <div className="mt-4">
              <div className="mb-1 text-xs font-medium text-slate-800">Root est_cost, Postgres units</div>
              <HBars digits={0} bars={[
                { label: "baseline plan", value: root(opt.nodes), color: SERIES.blue },
                { label: "with the index", value: root(opt.hypopg), color: SERIES.aqua, note: "HypoPG hypothetical index, /v1/simulate/hypopg" },
              ]} />
            </div>
          )}
        </ChartCard>

        <ChartCard title={`Node ${node.node_id}: ${node.op}${node.relation ? ` on ${label(node.relation)}` : ""}`} caption={<>{spec._source}. Log features use log1p, as in features.py.</>}>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="rounded border border-accent/40 bg-accent-soft px-1.5 py-0.5 font-mono text-ink">op {opIndex(spec.ops, node.op)} of {spec.ops.length}</span>
              <span className="text-slate-600">one-hot, then {spec.numeric.length} numbers:</span>
            </div>
            {!!node.filter_cols?.length && (
              <div className="text-xs text-slate-700">filter columns: <span className="font-mono text-slate-900">{node.filter_cols.map(label).join(", ")}</span></div>
            )}
            <HBars digits={2} bars={spec.numeric.map((k, i) => ({ label: k, value: f[i], color: SERIES.blue }))} />
            {ratio !== null && (
              <div className={cn("flex items-start gap-2 rounded-lg border p-2 text-xs", ratio >= spec.misestimate_ratio_alert ? "border-signal/40 bg-signal-soft text-ink" : "glass-subtle text-slate-700")}>
                {ratio >= spec.misestimate_ratio_alert && <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-signal" />}
                <span>Expected {int(node.est_rows)} rows, got {int(node.actual_rows!)}: {ratio.toFixed(1)}x off{ratio >= spec.misestimate_ratio_alert ? `, past the ${spec.misestimate_ratio_alert}x alert: run ANALYZE` : ""}.</span>
              </div>
            )}
          </div>
        </ChartCard>
      </div>

      {opt.explain && (
        <ChartCard title="Why the plan is slow" caption={<>/ai/gnn/explain at ask time, estimator {opt.explain.estimator}: {opt.explain.label}. Alert ratio {opt.explain.misestimate_alert_ratio}x (config.yaml gnn.misestimate_ratio_alert). Hover a bar to find the node in the tree.</>}>
          <div className="grid gap-4 md:grid-cols-[auto_1fr]">
            <BigNumber value={`${opt.explain.predicted_total_ms.toFixed(1)} ms`} label="predicted total" />
            <div className="space-y-1.5" onMouseLeave={() => setHl(null)}>
              {opt.explain.top_nodes.map((n) => (
                <div key={n.node_id} onMouseEnter={() => hover(n.node_id)} className={cn("grid cursor-default grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-2 rounded px-1 text-xs transition-colors", hl === n.node_id && "bg-accent-soft")}>
                  <span className="truncate text-slate-700">node {n.node_id} {n.op}{n.relation ? <span className="font-mono text-slate-500"> {label(n.relation)}</span> : null}</span>
                  <div className="h-5 py-0.5"><div className="h-full rounded-r-[4px] transition-opacity" style={{ width: `${(n.predicted_share_pct / explainMax) * 100}%`, background: SERIES.blue, opacity: hl === null || hl === n.node_id ? 1 : 0.45 }} /></div>
                  <span className="font-mono text-slate-900">{n.predicted_share_pct.toFixed(1)}% <span className="text-slate-500">{n.predicted_self_ms.toFixed(1)} ms</span></span>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-3 space-y-2">
            {opt.explain.misestimates.length === 0 && <div className="text-xs text-slate-600">No node past the {opt.explain.misestimate_alert_ratio}x misestimate alert.</div>}
            {opt.explain.misestimates.map((x) => (
              <div key={x.node_id} className="flex items-start gap-2 rounded-lg border border-signal/40 bg-signal-soft p-2 text-xs text-ink">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-signal" />
                <span>Node {x.node_id} {x.op}{x.relation ? ` on ${label(x.relation)}` : ""}: expected {int(x.est_rows)} rows, got {int(x.actual_rows)} ({x.ratio}x). {x.recommend}.</span>
              </div>
            ))}
          </div>
        </ChartCard>
      )}

      <ChartCard title="When the GNN serves" caption={<>Rule from models/gnn/NOTES.md: the GNN serves only when its scored median q-error is below the Postgres baseline&apos;s. Defaults are the dated reference scores. {m.gnn.source}</>}>
        <div className="grid items-center gap-4 md:grid-cols-[1fr_1fr_auto]">
          {[["GNN median q-error", gnn, setGnn], ["Postgres median q-error", pg, setPg]].map(([label, v, set]) => (
            <label key={label as string} className="block text-xs text-slate-700">
              <span className="flex justify-between"><span>{label as string}</span><span className="font-mono text-slate-900">{(v as number).toFixed(2)}</span></span>
              <input type="range" min={1} max={5} step={0.01} value={v as number} onChange={(e) => (set as (n: number) => void)(Number(e.target.value))} className="w-full accent-accent" />
            </label>
          ))}
          <div className={cn("rounded-lg border px-3 py-2 text-sm font-medium", who === "gnn" ? "border-accent/40 bg-accent-soft text-ink" : "border-signal/40 bg-signal-soft text-ink")}>
            serves: {who === "gnn" ? "GNN" : "Postgres baseline"}
          </div>
        </div>
        <div className="mt-3 rounded-md border border-signal/40 bg-signal-soft px-2 py-1 font-mono text-xs text-ink">{b?.estimator?.label ?? run.search.estimator_label}</div>
      </ChartCard>
    </div>
  );
}
