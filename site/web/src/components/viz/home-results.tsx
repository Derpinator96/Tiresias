"use client";
// The overview bento, from the run view (the current bundle, or the run record).
// Holds no literal numbers (tests/spans.test.mjs).
import type { ReactNode } from "react";
import { ShieldCheck } from "lucide-react";
import { Bento, ChartCard, Gauge } from "@/components/viz/charts";
import { Source } from "@/components/playground/bits";
import { RunBanner } from "@/components/viz/run-banner";
import { Waterfall } from "@/components/viz/waterfall";
import { q1Spans } from "@/lib/spans";
import { useView } from "@/lib/view";

const LIFT = "transition-transform duration-200 hover:-translate-y-0.5 motion-reduce:transition-none";

export function HomeResults({ hero }: { hero: ReactNode }) {
  const v = useView();
  const what = v.live ? v.templateId : "Q1";
  const fix = !v.live ? "one index" : v.actions.length === 1 ? v.actions[0] : `${v.actions.length} actions`;
  const line = v.live ? `bundle ${v.id}` : `${v.id}, synthetic data, ${v.heroRows?.toLocaleString("en-US")} rows, one machine`;
  return (
    <>
      <RunBanner className="mb-3" />
      <Bento>
        <div className="glass flex flex-col justify-between gap-5 p-6 md:col-span-7">{hero}</div>
        <ChartCard title={`${what} with ${fix}`} caption={`${v.src.twin}; median of ${v.runs ?? "?"} runs`} className="flex flex-col md:col-span-5">
          {v.speedupPct === null
            ? <p className="text-sm text-slate-600">No twin measurement in this bundle</p>
            : <Gauge value={v.speedupPct} digits={1} unit="%" label="faster on the twin" />}
          <div className="mt-2 text-center font-mono text-xs text-slate-600">
            {v.twinBefore ?? "?"} ms to {v.twinAfter ?? "?"} ms
          </div>
        </ChartCard>

        <ChartCard title="Where the time goes" caption={`${v.src.twin}; spans laid end to end, not concurrent`} className="md:col-span-8">
          <Waterfall spans={q1Spans(v)} />
        </ChartCard>
        <div className="flex flex-col gap-3 md:col-span-4">
          <div className={`tile-ink flex-1 p-5 ${LIFT}`}>
            <div className="flex items-center justify-between text-sm text-white/70">
              {v.canaryHits ? "Canary hits" : "Nothing leaked"}<ShieldCheck className="size-5 text-lime" aria-hidden />
            </div>
            <div className="mt-2 text-4xl font-light">{v.canaryHits}<span className="text-lg text-white/60"> of {v.canariesPlanted}</span></div>
            <div className="text-xs text-white/60">
              canaries in {v.payloads} payloads{v.llmPayloads !== null && `, ${v.llmPayloads} to the LLM`}
            </div>
            <div className="mt-1 text-xs text-white/40">{line}</div>
          </div>
          <div className={`tile-lime flex-1 p-5 ${LIFT}`}>
            <div className="text-sm">What the fix costs</div>
            <div className="mt-2 flex flex-wrap items-end gap-x-6 gap-y-2">
              <div><div className="text-4xl font-light">{v.storageMb ?? "?"}<span className="text-lg"> MB</span></div><div className="text-xs">index on disk</div></div>
              <div><div className="text-4xl font-light">+{v.writeCostMs}<span className="text-lg"> ms</span></div><div className="text-xs">per insert</div></div>
            </div>
            <div className="mt-1 text-xs">query result {v.checksumMatch ? "identical" : "differs"}{v.live && `; number checker ${v.llm.checker ?? "not run"}`}</div>
            <Source>storage: {v.src.twin}; write cost: {v.src.writeCost}; checksum: {v.src.checksum}</Source>
          </div>
        </div>
      </Bento>
    </>
  );
}
