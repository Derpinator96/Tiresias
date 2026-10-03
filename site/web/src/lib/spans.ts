// Spans for the waterfall charts, derived from the run view. No imports: tests load this file.
// The spans are laid end to end on one axis for comparison; they did not run concurrently.

export type Span = { id: string; label: string; start: number; dur: number; kind: "measured" | "predicted"; tone: "baseline" | "after" | "neutral"; note: string };

/** The figures a Q1 waterfall needs: the shape of src/lib/run-view.ts RunView, so a view can be
 *  passed as is. Nulls (a figure the bundle lacks) leave that span out. */
export type SpanInput = {
  meanBefore: number | null; twinBefore: number | null; twinAfter: number | null; runs: number | null; storageMb: number | null;
  predictedBefore: number | null; predictedAfter: number | null; estimatorLabel: string;
};

export function q1Spans(v: SpanInput): Span[] {
  const all: (Omit<Span, "start" | "dur"> & { dur: number | null })[] = [
    { id: "prod", label: "pg-prod, no index", dur: v.meanBefore, kind: "measured", tone: "baseline", note: "mean on production data" },
    { id: "twin-before", label: "twin, before", dur: v.twinBefore, kind: "measured", tone: "baseline", note: `median of ${v.runs} runs on the twin` },
    { id: "twin-after", label: "twin, after", dur: v.twinAfter, kind: "measured", tone: "after", note: `median of ${v.runs} runs; storage ${v.storageMb} MB` },
    { id: "pred-before", label: "predicted, before", dur: v.predictedBefore, kind: "predicted", tone: "baseline", note: v.estimatorLabel },
    { id: "pred-after", label: "predicted, after", dur: v.predictedAfter, kind: "predicted", tone: "after", note: v.estimatorLabel },
  ];
  const rows = all.filter((r): r is Omit<Span, "start"> => r.dur !== null);
  let t = 0;
  return rows.map((r) => {
    const s = { ...r, start: t };
    t += r.dur;
    return s;
  });
}

/** Round tick positions for an axis of length max: about n ticks on 1, 2 or 5 x 10^k. */
export function niceTicks(max: number, n = 5): number[] {
  const raw = max / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw)!;
  const out: number[] = [];
  for (let v = 0; v <= max + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

export const end = (spans: Span[]) => Math.max(...spans.map((s) => s.start + s.dur));
