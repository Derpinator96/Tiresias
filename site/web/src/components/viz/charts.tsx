"use client";
// Small chart kit for the site. Light only. Colours: categorical slots 1 to 3 of the dataviz
// reference palette (blue, orange, aqua), validated with its scripts/validate_palette.js on
// 2026-10-04: blue + orange pass every check; aqua is below 3:1 contrast, so every bar carries a
// visible value label and every chart a screen-reader table. Bars <= 24px, 4px rounded data end,
// one axis per chart, hover tooltip on every mark.
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { Source } from "@/components/playground/bits";
import { cn } from "@/lib/utils";

// Two series only (human request 2026-10-04): the accent and the signal colour of globals.css.
// Reference palette (2026-10-04): ink for the primary series, signal orange for slow, grey for the rest.
export const SERIES = { blue: "#262726", orange: "#e07a45", aqua: "#4c7bd9", lime: "#b7c93a", rose: "#cf5a70" } as const;

export function ChartCard({ title, caption, children, className }: { title: string; caption?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <figure className={cn("glass min-w-0 p-5", className)}>
      <figcaption className="mb-3 text-base font-semibold text-slate-900">{title}</figcaption>
      {children}
      {caption && <div className="mt-2"><Source>{caption}</Source></div>}
    </figure>
  );
}

function SrTable({ rows, head }: { rows: (string | number)[][]; head: string[] }) {
  return (
    <div className="sr-only"><table>
      <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

export type Bar = { label: string; value: number; color: string; note?: string };

/** Horizontal bars from one zero baseline; optional dashed reference line. */
export function HBars({ bars, unit = "", digits = 1, refLine, max }: { bars: Bar[]; unit?: string; digits?: number; refLine?: { value: number; label: string }; max?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const grown = useGrown();
  const top = (max ?? Math.max(...bars.map((b) => b.value), refLine?.value ?? 0)) * 1.18;
  const pct = (v: number) => `${(v / top) * 100}%`;
  const grow = "transition-all duration-700 ease-out motion-reduce:transition-none";
  const fmt = (v: number) => `${v.toFixed(digits)}${unit}`;
  return (
    <div className="relative">
      <div className="space-y-2">
        {bars.map((b, i) => (
          <div key={b.label} className="grid grid-cols-[minmax(0,7.5rem)_1fr] items-center gap-2" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <span className="truncate text-xs text-slate-700" title={b.label}>{b.label}</span>
            <div className="relative h-6">
              <div className={cn("absolute inset-y-0.5 left-0 rounded-r-[4px]", grow)} style={{ width: pct(b.value * grown), transitionDelay: `${i * 60}ms`, background: b.color, opacity: hover === null || hover === i ? 1 : 0.45 }} />
              <span className={cn("absolute top-1/2 -translate-y-1/2 pl-1.5 font-mono text-xs font-semibold text-slate-900", grow)} style={{ left: pct(b.value * grown), transitionDelay: `${i * 60}ms` }}>{fmt(b.value)}</span>
              {hover === i && b.note && (
                <div className="glass-strong absolute bottom-full left-0 z-10 mb-1 max-w-64 rounded-lg px-2 py-1 text-xs text-slate-700">{b.label}: {fmt(b.value)}. {b.note}</div>
              )}
            </div>
          </div>
        ))}
      </div>
      {refLine && (
        <div className="pointer-events-none absolute inset-y-0 left-[calc(7.5rem+0.5rem)] right-0">
          <div className="absolute inset-y-[-6px] border-l border-dashed border-slate-500" style={{ left: pct(refLine.value) }}>
            <span className="absolute -top-4 left-1 whitespace-nowrap text-xs text-slate-600">{refLine.label}</span>
          </div>
        </div>
      )}
      <SrTable head={["item", "value"]} rows={bars.map((b) => [b.label, fmt(b.value)])} />
    </div>
  );
}

/** One line with markers and an optional dashed threshold; tooltip on the nearest point. */
export function LineChart({ points, threshold, yMax, digits = 4 }: { points: { label: string; value: number }[]; threshold?: { value: number; label: string }; yMax: number; digits?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 420, H = 180, L = 36, R = 16, T = 16, B = 34;
  const x = (i: number) => L + (i * (W - L - R)) / Math.max(1, points.length - 1);
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);
  const ticks = [0, yMax / 2, yMax];
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="line chart">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#e2e8f0" />
            <text x={L - 6} y={y(t) + 3} textAnchor="end" className="fill-slate-500 text-xs">{t}</text>
          </g>
        ))}
        {threshold && (
          <g>
            <line x1={L} x2={W - R} y1={y(threshold.value)} y2={y(threshold.value)} stroke="#64748b" strokeDasharray="4 3" />
            <text x={W - R} y={y(threshold.value) - 4} textAnchor="end" className="fill-slate-600 text-xs">{threshold.label}</text>
          </g>
        )}
        <polyline points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} fill="none" stroke={SERIES.blue} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <g key={p.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={x(i) - 30} y={T} width={60} height={H - T - B} fill="transparent" />
            <circle cx={x(i)} cy={y(p.value)} r={hover === i ? 6 : 4.5} fill={SERIES.blue} stroke="white" strokeWidth={2} />
            <text x={x(i)} y={H - 12} textAnchor="middle" className="fill-slate-600 text-xs">{p.label}</text>
          </g>
        ))}
        <text x={x(points.length - 1) - 8} y={y(points.at(-1)!.value) - 10} textAnchor="end" className="fill-slate-900 font-mono text-xs font-semibold">{points.at(-1)!.value}</text>
      </svg>
      {hover !== null && (
        <div className="glass-strong pointer-events-none absolute top-0 rounded-lg px-2 py-1 font-mono text-xs text-slate-800" style={{ left: `${(x(hover) / W) * 100}%`, transform: "translateX(-50%)" }}>
          {points[hover].label}: {points[hover].value.toFixed(digits)}
        </div>
      )}
      <SrTable head={["point", "value"]} rows={points.map((p) => [p.label, p.value])} />
    </div>
  );
}

/** Part of a whole: one bar split into segments with 2px gaps, labelled below. */
export function PartBar({ parts, total, unit = "" }: { parts: { label: string; value: number; color: string }[]; total?: number; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const sum = total ?? parts.reduce((a, p) => a + p.value, 0);
  const rest = sum - parts.reduce((a, p) => a + p.value, 0);
  return (
    <div>
      <div className="flex h-6 gap-0.5 overflow-hidden rounded-[4px]">
        {parts.map((p, i) => (
          <div key={p.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} className="h-full transition-opacity" style={{ width: `${(p.value / sum) * 100}%`, background: p.color, opacity: hover === null || hover === i ? 1 : 0.5 }} title={`${p.label}: ${p.value}${unit}`} />
        ))}
        {rest > 0 && <div className="h-full flex-1 bg-slate-200/80" />}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: p.color }} aria-hidden />
            {p.label} <span className="font-mono font-semibold text-slate-900">{p.value}{unit}</span>
          </span>
        ))}
        {rest > 0 && <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-slate-200" aria-hidden />unused <span className="font-mono font-semibold text-slate-900">{Number(rest.toFixed(2))}{unit}</span></span>}
      </div>
    </div>
  );
}

/** A left-to-right chain of steps that wraps on small screens. */
export function Flow({ steps }: { steps: { label: string; sub?: string; tone?: "private" | "ai" | "check" }[] }) {
  // Monochrome: the AI side is a deeper grey, a check step is ink.
  const tone = { private: "glass-subtle text-slate-900", ai: "bg-slate-200/70 text-slate-900", check: "bg-ink text-white" };
  return (
    <ol className="flex flex-wrap items-center gap-1.5">
      {steps.map((s, i) => (
        <Fragment key={i}>
          {i > 0 && <ArrowRight className="size-4 shrink-0 text-slate-400" aria-hidden />}
          <li className={cn("rounded-full px-3 py-1.5", tone[s.tone ?? "private"])}>
            <div className="text-xs font-medium">{s.label}</div>
            {s.sub && <div className={cn("font-mono text-xs", s.tone === "check" ? "text-white/70" : "text-slate-600")}>{s.sub}</div>}
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

export function BigNumber({ value, label, tone = "default" }: { value: string; label: string; tone?: "default" | "good" }) {
  return (
    <div>
      <div className={cn("font-mono text-3xl font-semibold tracking-tight [overflow-wrap:anywhere]", tone === "good" ? "text-accent" : "text-slate-900")}>{value}</div>
      <div className="mt-0.5 text-xs text-slate-600">{label}</div>
    </div>
  );
}

/** Compact 12-column grid for every page (reference 2026-10-04). Children set their own
 *  col-span / row-span; one column below md. */
// Tiles fade up once on first paint, staggered by position (nth-child animation-delay, tw-animate-css
// keyframes); fill-mode backwards so the hover lift still works after; none under reduced motion.
const FADE_UP = "*:animate-in *:fade-in *:slide-in-from-bottom-2 *:animation-duration-500 *:fill-mode-backwards motion-reduce:*:animate-none " +
  "*:nth-2:[animation-delay:60ms] *:nth-3:[animation-delay:120ms] *:nth-4:[animation-delay:180ms] *:nth-5:[animation-delay:240ms] *:nth-6:[animation-delay:300ms] *:nth-[n+7]:[animation-delay:360ms]";
export function Bento({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-1 gap-3 md:grid-cols-12", FADE_UP, className)}>{children}</div>;
}

/** 0 on the first render, 1 a moment later, so bars and dials can transition in from zero.
 *  A timer, not requestAnimationFrame: rAF never fires in a background tab, which left dials at 0. */
export function useGrown(): number {
  const [on, setOn] = useState(0);
  useEffect(() => { const t = setTimeout(() => setOn(1), 30); return () => clearTimeout(t); }, []);
  return on;
}

/** Semicircle dial like the reference's score gauge: value between min and max, a lime knob at
 *  the value, big light number in the middle. Sweeps in on mount (none under reduced motion). */
export function Gauge({ value, min = 0, max = 100, label, unit = "", digits = 0, tone = "light" }: {
  value: number; min?: number; max?: number; label: string; unit?: string; digits?: number; tone?: "light" | "dark";
}) {
  const shown = useGrown();
  const f = Math.max(0, Math.min(1, (value - min) / (max - min || 1))) * shown;
  const r = 80, len = Math.PI * r;
  const a = Math.PI * (1 - f), kx = 100 + r * Math.cos(a), ky = 100 - r * Math.sin(a);
  const ink = tone === "dark" ? "#ffffff" : "#262726";
  return (
    <div className="relative mx-auto w-full max-w-[240px] pb-1" role="img" aria-label={`${label}: ${value.toFixed(digits)}${unit}`}>
      <svg viewBox="0 0 200 112" className="w-full">
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke={tone === "dark" ? "rgb(255 255 255 / 0.15)" : "#e4e7e4"} strokeWidth={10} strokeLinecap="round" strokeDasharray="2 4" />
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke={ink} strokeWidth={10} strokeLinecap="round"
          strokeDasharray={len} strokeDashoffset={len * (1 - f)} className="transition-[stroke-dashoffset] duration-1000 ease-out motion-reduce:transition-none" />
        <circle cx={kx} cy={ky} r={9} fill="#f0ff97" stroke={ink} strokeWidth={2} className="transition-all duration-1000 ease-out motion-reduce:transition-none" />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className={cn("text-3xl font-light tracking-tight xl:text-4xl", tone === "dark" ? "text-white" : "text-ink")}>{value.toFixed(digits)}<span className="text-lg">{unit}</span></div>
        <div className={cn("text-xs", tone === "dark" ? "text-white/60" : "text-slate-500")}>{label}</div>
      </div>
    </div>
  );
}

/** Animates a number from its previous value to the new one (600 ms ease-out); instant under
 *  reduced motion. Used so fresh results visibly arrive. */
export function useCountUp(value: number, ms = 600): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const start = from.current, t0 = performance.now();
    let id = 0;
    const step = () => {
      const k = reduce ? 1 : Math.min(1, (performance.now() - t0) / ms);
      const v = start + (value - start) * (1 - (1 - k) ** 3);
      from.current = v;
      setShown(v);
      if (k < 1) id = window.setTimeout(step, 16); // a timer, not rAF: keeps working in background tabs
    };
    id = window.setTimeout(step, 0);
    return () => clearTimeout(id);
  }, [value, ms]);
  return shown;
}
