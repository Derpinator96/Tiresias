"use client";
// Span waterfall: one row per span on a shared time axis, a scrub cursor, hatched bars for
// predicted values, hover detail. Fully data driven: pass spans, get the chart.
import { useEffect, useMemo, useState } from "react";
import { Pause, Play, RotateCcw } from "lucide-react";
import { end, niceTicks, type Span } from "@/lib/spans";
import { SERIES } from "@/components/viz/charts";
import { cn } from "@/lib/utils";

const TONE = { baseline: SERIES.orange, after: SERIES.blue, neutral: SERIES.aqua } as const;
const LABEL_ROOM = 1.25;
const fmt = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${v.toFixed(1)} ms`);

export function Waterfall({ spans, title }: { spans: Span[]; title?: string }) {
  const total = useMemo(() => end(spans), [spans]);
  const ticks = useMemo(() => niceTicks(total), [total]);
  const axis = Math.max(ticks.at(-1)! + (ticks[1] - ticks[0]) * Number(ticks.at(-1)! < total), total * LABEL_ROOM); // room for the last value label
  const [pos, setCursor] = useState<number | null>(null); // null: the end of the data, so new spans reset it
  const cursor = pos ?? total;
  const [playing, setPlaying] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [hidePred, setHidePred] = useState(false);
  const shown = hidePred ? spans.filter((s) => s.kind === "measured") : spans;

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setCursor((c) => ((c ?? total) >= axis ? (setPlaying(false), axis) : Math.min(axis, (c ?? total) + axis / ticks.length / ticks.length))), 40);
    return () => clearInterval(t);
  }, [playing, axis, total, ticks.length]);

  const x = (v: number) => `${(v / axis) * 100}%`;
  const h = shown.find((s) => s.id === hover);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <button className="inline-flex h-7 items-center gap-1 rounded-md bg-slate-900 px-2 text-white hover:bg-slate-800" onClick={() => { if (cursor >= total) setCursor(0); setPlaying(!playing); }}>
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : "Play"}
        </button>
        <button className="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white/70 px-2 text-slate-700 hover:bg-white" onClick={() => { setPlaying(false); setCursor(null); }}>
          <RotateCcw className="size-3.5" /> Reset
        </button>
        <label className="inline-flex items-center gap-1.5 text-slate-700">
          <input type="checkbox" className="size-3.5 accent-slate-900" checked={!hidePred} onChange={(e) => setHidePred(!e.target.checked)} /> show predicted
        </label>
        <span className="ml-auto font-mono text-slate-700">{title ? `${title} ` : ""}cursor {fmt(cursor)}</span>
      </div>

      <div className="relative">
        <div className="grid grid-cols-[minmax(0,8.5rem)_1fr] gap-2">
          <div />
          <div className="relative h-4">
            {ticks.map((t) => <span key={t} className="absolute -translate-x-1/2 font-mono text-[10px] text-slate-500" style={{ left: x(t) }}>{fmt(t)}</span>)}
          </div>
          {shown.map((s) => {
            const done = Math.min(1, Math.max(0, (cursor - s.start) / s.dur));
            return (
              <div key={s.id} className="contents" onMouseEnter={() => setHover(s.id)} onMouseLeave={() => setHover(null)}>
                <span className={cn("truncate self-center text-xs text-slate-700", hover === s.id && "font-medium text-slate-900")} title={s.label}>{s.label}</span>
                <div className="relative h-7 border-t border-slate-200/70">
                  <div className="absolute top-1 h-5 overflow-hidden rounded-[4px]" style={{ left: x(s.start), width: x(s.dur), minWidth: 3, opacity: hover && hover !== s.id ? 0.5 : 1 }}>
                    <div className="absolute inset-0" style={{ background: s.kind === "predicted" ? `repeating-linear-gradient(135deg, ${TONE[s.tone]} 0 4px, rgba(255,255,255,0.55) 4px 8px)` : TONE[s.tone], opacity: 0.28 }} />
                    <div className="absolute inset-y-0 left-0" style={{ width: `${done * 100}%`, background: s.kind === "predicted" ? `repeating-linear-gradient(135deg, ${TONE[s.tone]} 0 4px, rgba(255,255,255,0.55) 4px 8px)` : TONE[s.tone] }} />
                  </div>
                  <span className="absolute top-1/2 -translate-y-1/2 pl-1.5 font-mono text-[11px] font-semibold text-slate-900" style={{ left: `calc(${x(s.start + s.dur)})` }}>{fmt(s.dur)}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="pointer-events-none absolute bottom-0 top-4 left-[calc(8.5rem+0.5rem)] right-0">
          <div className="absolute inset-y-0 border-l border-dashed border-red-500" style={{ left: x(cursor) }}>
            <span className="absolute -top-1 -left-1 size-2 rounded-sm bg-red-500" />
          </div>
        </div>
      </div>

      <input type="range" min={0} max={axis} step={axis / 400} value={cursor} onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }} className="mt-2 w-full accent-red-500" aria-label="time cursor" />
      <p className="mt-1 min-h-8 text-[11px] leading-snug text-slate-700">
        {h ? <><span className="font-medium text-slate-900">{h.label}</span>: {fmt(h.dur)}, {h.kind}. {h.note}.</> : "Hover a row for its source. Hatched bars are predictions, solid bars are measurements."}
      </p>
      <div className="sr-only"><table><tbody>{spans.map((s) => <tr key={s.id}><td>{s.label}</td><td>{s.start}</td><td>{s.dur}</td><td>{s.kind}</td></tr>)}</tbody></table></div>
    </div>
  );
}
