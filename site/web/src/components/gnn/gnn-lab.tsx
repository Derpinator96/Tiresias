"use client";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Eye, Hash, Pause, Play, TriangleAlert } from "lucide-react";
import { Bento, ChartCard, Gauge, HBars, SERIES } from "@/components/viz/charts";
import { Source } from "@/components/playground/bits";
import { argmax, layout, misestimate, numericFeatures, opIndex, planOptions, predictedShares, qError, reach, shares, type PlanNode } from "@/lib/gnn";
import { name, useBundle } from "@/lib/context";
import type { Bundle, Explain, Prediction } from "@/lib/bundle";
import { GNN_SERVING, run } from "@/lib/facts";
import plans from "@/data/gnn_plans.json";
import spec from "@/data/gnn_spec.json";
import m from "@/data/measurements.json";
import { cn } from "@/lib/utils";

const seg = (on: boolean) => cn("h-7 whitespace-nowrap pill px-3 text-sm", on ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70");
const Seg = ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={cn("glass-subtle flex w-fit flex-wrap pill p-0.5", className)}>{children}</div>;
const nFeatures = spec.ops.length + spec.numeric.length;
const STEPS = ["Plan", "Features", "Message passing", "Prediction"] as const;
const MODE_LABEL = { cost: "Postgres cost", time: "measured time", gnn: "GNN predicted time" } as const;

// Tree geometry in pixels: layout() gives x in leaf units and y in depth levels.
// Boxes hold two 13px lines (20px line height each) plus padding; the tooltip rows are 20px.
const BOX_W = 168, BOX_H = 64, COL = 192, ROW = 112, PAD = 12, TIP_W = 224, TIP_ROW = 20;
// SVG strokes: slate-300, ink, ink (CSS classes cannot colour an SVG marker here)
const EDGE = { idle: "rgb(203 213 225)", reach: SERIES.blue, hot: "rgb(15 23 42)" } as const;
// lime (--color-lime) at an alpha proportional to the share relative to the hottest node, over white
const heat = (s: number) => `linear-gradient(rgb(240 255 151 / ${s.toFixed(3)}), rgb(240 255 151 / ${s.toFixed(3)})), #fff`;
const pct = (s: number) => `${(s * 100).toFixed(1)}%`;
const int = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

type Option = { id: string; label: string; nodes: PlanNode[]; prediction?: Prediction | null; explain?: Explain | null; hypopg?: PlanNode[] };

/** One plan per picker entry: the bundle's logged plans (plans[tid][0]) or the illustrative ones. */
function options(b: Bundle | null): Option[] {
  if (!b || !planOptions(b).length) return plans.plans.filter((p) => !("invented" in p)).map((p) => ({ id: p.id, label: p.label, nodes: p.nodes as PlanNode[] }));
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
  const [step, setStep] = useState(0);
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
  const hottest = Math.max(...share) || 1;
  const feats = useMemo(() => numericFeatures(nodes), [nodes]);
  const passing = step === 2;   // only the message-passing step dims the nodes outside the reach
  const seen = useMemo(() => reach(nodes, sel, layers), [nodes, sel, layers]);
  const node = nodes[sel] ?? nodes[0];
  const f = feats[sel] ?? feats[0];
  const ratio = node.actual_rows === undefined ? null : misestimate(node.est_rows, node.actual_rows);
  const label = (code: string | undefined) => (code ? (real ? name(b, code) : code) : "");
  const root = (ns: PlanNode[]) => ns.find((n) => n.parent_id === null)?.est_cost ?? 0;
  const slow = nodes[argmax(share)];

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

  const pick = (id: string) => { setPlanId(id); setSel(0); setVariant("baseline"); };
  const goto = (i: number) => {
    setStep(i);
    if (i === 2) { setLayers(0); setPlaying(true); } else setPlaying(false);
    if (i === 3 && gnnMode) setBy("gnn");
  };
  const clickNode = (i: number) => { setSel(i); if (step === 0) setStep(1); };

  // Step 4 figures: the serving estimator's predicted total against the logged plan's measured total.
  const predicted = variant === "baseline" ? opt.prediction?.total_ms ?? opt.explain?.predicted_total_ms ?? null : null;
  const measured = timed ? nodes.reduce((a, n) => a + (n.self_ms ?? 0), 0) : null;
  const q = predicted !== null && measured !== null ? qError(predicted, measured) : null;
  const [gnnRef, , pgRef] = m.gnn.models;
  const alerts = opt.explain && variant === "baseline"
    ? opt.explain.misestimates
    : nodes.filter((n) => n.actual_rows !== undefined && misestimate(n.est_rows, n.actual_rows) >= spec.misestimate_ratio_alert)
      .map((n) => ({ node_id: n.node_id, op: n.op, relation: n.relation, est_rows: n.est_rows, actual_rows: n.actual_rows!, ratio: Number(misestimate(n.est_rows, n.actual_rows!).toFixed(1)), recommend: "run ANALYZE" }));
  const explainMax = Math.max(...(opt.explain?.top_nodes.map((n) => n.predicted_share_pct) ?? [1]));
  const drop = opt.hypopg && root(opt.nodes) > 0 ? 100 * (1 - root(opt.hypopg) / root(opt.nodes)) : null;

  return (
    <div className="space-y-3">
      <div className="glass-bar flex flex-wrap items-center gap-2 p-2">
        <label className="glass-subtle relative flex h-8 min-w-0 max-w-full items-center pill sm:max-w-96">
          <span className="sr-only">Query</span>
          <select value={opt.id} onChange={(e) => pick(e.target.value)} title={b ? name(b, opt.id) : undefined}
            className="h-full w-full min-w-0 appearance-none truncate pill bg-transparent pl-3 pr-8 font-mono text-sm text-ink outline-none">
            {opts.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2.5 size-4 text-slate-500" aria-hidden />
        </label>
        {opt.hypopg && (
          <Seg>
            <button className={seg(variant === "baseline")} onClick={() => { setVariant("baseline"); setSel(0); }}>Baseline</button>
            <button className={seg(variant === "hypopg")} onClick={() => { setVariant("hypopg"); setSel(0); }}>With index</button>
          </Seg>
        )}
        <Seg>
          <span className="flex h-7 items-center px-2 text-xs text-slate-500">Colour by</span>
          <button className={seg(mode === "cost")} onClick={() => setBy("cost")}>Cost</button>
          {timed && <button className={seg(mode === "time")} onClick={() => setBy("time")}>Time</button>}
          {gnnMode && <button className={seg(mode === "gnn")} onClick={() => setBy("gnn")}>GNN</button>}
        </Seg>
        {b && (
          <button onClick={() => setReal(!real)} aria-pressed={!real} title={real ? "showing real names; switch to what the AI sees" : "showing what the AI sees; switch to real names"}
            className="glass-subtle ml-auto inline-flex h-8 items-center gap-1.5 pill px-3 text-sm text-ink hover:bg-slate-200/70">
            {real ? <Eye className="size-4" /> : <Hash className="size-4" />}{real ? "Real names" : "AI view"}
          </button>
        )}
      </div>

      <Bento>
        <div className="flex min-w-0 flex-col gap-3 md:col-span-8">
          <ChartCard className="flex-1" title={`${variant === "hypopg" ? "Plan tree with the index" : "Plan tree"}, coloured by ${MODE_LABEL[mode]} share`} caption={b
            ? <>logged auto_explain plan, bundle {b.id}{mode === "gnn" ? `; predicted share: ${b.estimator?.label ?? opt.prediction?.estimator}` : ""}{variant === "hypopg" ? "; HypoPG plan, no actual rows or times" : ""}; AI-side labels are the gateway&apos;s HMAC codes</>
            : <>illustrative plan from docs/architecture.md, not from {run.run_id}; codes are illustrative. Ask a question to see real logged plans</>}>
            <div ref={wrap} className="inset-field max-h-[70vh] overflow-auto rounded-lg" onMouseLeave={() => setHl(null)}>
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
                    const on = passing && seen.has(n.node_id) && seen.has(n.parent_id!);
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
                    <button key={n.node_id} onClick={() => clickNode(i)} onMouseEnter={() => hover(n.node_id)} onMouseLeave={() => setHl(null)} onFocus={() => hover(n.node_id)} onBlur={() => setHl(null)} aria-pressed={sel === i} data-node={n.node_id}
                      className={cn("absolute overflow-hidden rounded-lg px-2.5 py-1.5 text-left transition-[translate,box-shadow,opacity] duration-150",
                        isHot ? "-translate-y-0.5 shadow-lg" : "shadow-(--glass-shadow)", sel === i && "ring-2 ring-ink", passing && !seen.has(n.node_id) && "opacity-40")}
                      style={{ left: cx - BOX_W / 2, top, width: BOX_W, height: BOX_H, background: heat(s / hottest) }}>
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
                    <div className="pointer-events-none fixed z-10 rounded-xl bg-white px-3 py-2 text-xs shadow-(--glass-shadow-lg)" style={{ left, top, width: TIP_W }}>
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
          </ChartCard>

          {drop !== null && opt.hypopg && (
            <div className="glass grid items-center gap-4 p-5 sm:grid-cols-[minmax(0,240px)_1fr]">
              <Gauge value={drop} digits={1} unit="%" label="root est_cost drop with the index" />
              <div className="space-y-1 text-sm text-slate-700">
                <div className="text-base font-semibold text-slate-900">The index cuts the plan cost</div>
                <div className="font-mono text-xs">{int(root(opt.nodes))} to {int(root(opt.hypopg))} Postgres cost units</div>
                <Source>HypoPG hypothetical index, /v1/simulate/hypopg; cost units, not milliseconds</Source>
              </div>
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-3 md:col-span-4">
          <div className="glass p-4">
            <div className="mb-2 text-sm font-semibold text-slate-900">How the GNN reads this plan</div>
            <ol className="flex flex-wrap gap-1">
              {STEPS.map((s, i) => (
                <li key={s}>
                  <button onClick={() => goto(i)} aria-current={step === i ? "step" : undefined}
                    className={cn("inline-flex h-7 items-center gap-1.5 whitespace-nowrap pill pl-1 pr-3 text-sm", step === i ? "bg-ink text-white" : "glass-subtle text-slate-600 hover:text-ink")}>
                    <span className={cn("flex size-5 items-center justify-center rounded-full text-xs", step === i ? "bg-lime text-ink" : "bg-white text-slate-600")}>{i + 1}</span>{s}
                  </button>
                </li>
              ))}
            </ol>
          </div>

          {step === 0 && (
            <>
              <div className="tile-ink p-5">
                <div className="text-xs text-white/60">Slowest node by {MODE_LABEL[mode]}</div>
                <div className="mt-1 text-4xl font-light tracking-tight">{pct(share[nodes.indexOf(slow)])}</div>
                <div className="mt-1 truncate text-sm">{slow.op}{slow.relation ? <span className="font-mono text-white/70"> on {label(slow.relation)}</span> : null}</div>
                {opt.explain && variant === "baseline" && (
                  <div className="mt-3 text-xs text-white/60">predicted total <span className="font-mono text-base text-white">{opt.explain.predicted_total_ms.toFixed(1)} ms</span></div>
                )}
                <button onClick={() => clickNode(nodes.indexOf(slow))} className="mt-3 inline-flex h-7 items-center pill bg-lime px-3 text-sm text-ink">Read its features</button>
              </div>
              {opt.explain && variant === "baseline" && (
                <div className="glass p-4">
                  <div className="mb-2 text-sm font-semibold text-slate-900">Predicted share, top nodes</div>
                  <div className="space-y-1" onMouseLeave={() => setHl(null)}>
                    {opt.explain.top_nodes.map((n) => (
                      <div key={n.node_id} onMouseEnter={() => hover(n.node_id)} className={cn("grid cursor-default grid-cols-[minmax(0,8rem)_1fr_auto] items-center gap-2 rounded-lg px-1 text-xs", hl === n.node_id && "bg-lime/60")}>
                        <span className="truncate text-slate-700">{n.op}{n.relation ? <span className="font-mono text-slate-500"> {label(n.relation)}</span> : null}</span>
                        <div className="h-4"><div className="h-full rounded-r-[4px]" style={{ width: `${(n.predicted_share_pct / explainMax) * 100}%`, background: SERIES.blue }} /></div>
                        <span className="font-mono text-slate-900">{n.predicted_share_pct.toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                  <Source>/ai/gnn/explain at ask time, {opt.explain.estimator}: {opt.explain.label}; hover a row to find the node</Source>
                </div>
              )}
            </>
          )}

          {step === 1 && (
            <div className="glass space-y-3 p-4">
              <div className="text-sm font-semibold text-slate-900">Node {node.node_id}: {node.op}{node.relation ? <span className="font-mono font-normal text-slate-600"> on {label(node.relation)}</span> : null}</div>
              <div className="flex flex-wrap gap-1.5 text-xs">
                <span className="glass-subtle pill px-2.5 py-0.5 font-mono text-slate-700">op {opIndex(spec.ops, node.op) + 1} of {spec.ops.length}</span>
                <span className="glass-subtle pill px-2.5 py-0.5 font-mono text-slate-700">{nFeatures} features</span>
                {!!node.filter_cols?.length && <span className="glass-subtle max-w-full truncate pill px-2.5 py-0.5 font-mono text-slate-700">filter {node.filter_cols.map(label).join(", ")}</span>}
              </div>
              <HBars digits={2} bars={spec.numeric.map((k, i) => ({ label: k, value: f[i], color: SERIES.blue }))} />
              {ratio !== null && ratio >= spec.misestimate_ratio_alert && (
                <div className="inset-field flex items-start gap-2 p-2 text-xs text-ink">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-signal" />
                  <span>{int(node.est_rows)} rows expected, {int(node.actual_rows!)} seen: {ratio.toFixed(1)}x off</span>
                </div>
              )}
              <Source>click a node to read its vector; one-hot op plus {spec.numeric.length} numbers, log features use log1p; {spec._source}</Source>
            </div>
          )}

          {step === 2 && (
            <div className="glass space-y-3 p-4">
              <div className="flex items-center gap-3">
                <button className="inline-flex h-8 items-center gap-1 pill bg-ink px-3 text-sm text-white hover:bg-slate-800" onClick={() => { if (layers >= spec.layers) setLayers(0); setPlaying(!playing); }}>
                  {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : "Play"}
                </button>
                <div className="text-4xl font-light tracking-tight text-ink">{layers}<span className="text-lg text-slate-500"> of {spec.layers} layers</span></div>
              </div>
              <input type="range" min={0} max={spec.layers} step={1} value={layers} aria-label="layers" onChange={(e) => { setPlaying(false); setLayers(Number(e.target.value)); }} className="w-full accent-ink" />
              <div className="text-sm text-slate-700"><span className="font-mono font-semibold text-ink">{seen.size} of {nodes.length}</span> nodes reach node {node.node_id}</div>
              <Source>{spec.message_passing}; hidden size {spec.hidden_size}, layer count from config.yaml gnn.layers; click a node to move the target</Source>
            </div>
          )}

          {step === 3 && (
            <>
              <div className="tile-lime space-y-3 p-5">
                <div className="text-xs text-slate-700">Predicted vs measured total</div>
                {predicted !== null && measured !== null ? (
                  <div className="flex flex-wrap items-end gap-x-5 gap-y-2">
                    <div><div className="font-mono text-3xl font-semibold">{predicted.toFixed(1)}</div><div className="text-xs text-slate-700">predicted ms</div></div>
                    <div><div className="font-mono text-3xl font-semibold">{measured.toFixed(1)}</div><div className="text-xs text-slate-700">measured ms</div></div>
                    {q !== null && <span className="pill bg-ink px-3 py-1 font-mono text-sm text-white">q-error {q.toFixed(2)}</span>}
                  </div>
                ) : (
                  <div className="text-sm">{variant === "hypopg" ? "No prediction for the HypoPG plan." : "No prediction for this plan: trained weights are not delivered."}</div>
                )}
                <Gauge value={gnnRef.median} min={1} max={pgRef.median} digits={2} label={`${gnnRef.label} median q-error`} />
                <div className="text-center text-xs text-slate-700">full dial: {pgRef.label} {pgRef.median}</div>
                <span className="inline-block max-w-full truncate pill bg-white/70 px-3 py-1 font-mono text-xs">serving: {b?.estimator?.label ?? GNN_SERVING}</span>
                <Source>measured: sum of node self_ms in the logged plan; q-error is max over min. Dial: {m.gnn.source}. The GNN serves only when its scored median q-error is below Postgres&apos;s.</Source>
              </div>
              <div className="glass space-y-2 p-4">
                <div className="text-sm font-semibold text-slate-900">Misestimates past {spec.misestimate_ratio_alert}x</div>
                {alerts.length === 0 && <div className="text-xs text-slate-600">None in this plan.</div>}
                {alerts.map((x) => (
                  <button key={x.node_id} onMouseEnter={() => hover(x.node_id)} onMouseLeave={() => setHl(null)} onClick={() => clickNode(nodes.findIndex((n) => n.node_id === x.node_id))}
                    className="inset-field flex w-full items-start gap-2 p-2 text-left text-xs text-ink">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-signal" />
                    <span>{x.op}{x.relation ? ` on ${label(x.relation)}` : ""}: {int(x.est_rows)} expected, {int(x.actual_rows)} seen ({x.ratio}x). {x.recommend}.</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </Bento>
    </div>
  );
}
