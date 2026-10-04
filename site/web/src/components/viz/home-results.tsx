"use client";
// The overview: the hero line, the architecture widget, then one compact row of four tiles, all
// from the run view (the current bundle, or the run record). Holds no literal numbers
// (tests/spans.test.mjs). Tiles showing bundle figures flash once when that bundle just arrived.
import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Architecture } from "@/components/viz/architecture";
import { Bento, Gauge, useCountUp, useGrown } from "@/components/viz/charts";
import { Source } from "@/components/playground/bits";
import { useContextStore } from "@/lib/context";
import { writeShare } from "@/lib/facts";
import { q1Spans } from "@/lib/spans";
import { useView } from "@/lib/view";
import { cn } from "@/lib/utils";

const TILE = "min-h-40 p-4 md:col-span-3";
const Num = ({ value }: { value: number }) => <>{Math.round(useCountUp(value)).toLocaleString("en-US")}</>;

export function HomeResults({ hero }: { hero: ReactNode }) {
  const v = useView();
  const fresh = useContextStore((s) => s.fresh);
  const flash = v.live && fresh === v.id ? "fresh-flash" : "";
  const k = (name: string) => `${name}-${flash ? fresh : "still"}`; // remount replays the flash
  const what = v.live ? v.templateId ?? "The query" : "Q1";
  const spans = q1Spans(v).filter((s) => s.kind === "measured");
  const most = Math.max(...spans.map((s) => s.dur));
  const grown = useGrown();
  return (
    <Bento>
      <div className="glass p-5 md:col-span-12">
        {hero}
        <div className="mt-4"><Architecture /></div>
      </div>

      <div key={k("speed")} className={cn("glass flex flex-col", TILE, flash)}>
        <div className="truncate text-xs text-slate-600" title={v.src.twin}>{what} on the twin, median of {v.runs ?? "?"} runs</div>
        {v.speedupPct === null
          ? <p className="mt-2 text-sm text-slate-600">No twin measurement in this bundle</p>
          : <div className="mx-auto w-full max-w-[150px] [&_.tracking-tight]:text-2xl!"><Gauge value={v.speedupPct} digits={1} unit="%" label="faster" /></div>}
        <div className="text-center font-mono text-xs text-slate-600">{v.twinBefore ?? "?"} ms to {v.twinAfter ?? "?"} ms</div>
        {v.twinTag && <div className="text-center text-xs text-slate-600">{v.twinTag}</div>}
      </div>

      <div key={k("canary")} className={cn("tile-ink", TILE, flash)}>
        <div className="flex items-center justify-between text-xs text-white/70">
          {v.canaryHits ? "Canary hits" : "Nothing leaked"}<ShieldCheck className="size-4 text-lime" aria-hidden />
        </div>
        <div className="mt-2 text-4xl font-light"><Num value={v.canaryHits} /><span className="text-lg text-white/60"> of {v.canariesPlanted}</span></div>
        <div className="text-xs text-white/60">canaries in <Num value={v.payloads} /> payloads{v.llmPayloads !== null && `, ${v.llmPayloads} to the LLM`}</div>
        <div className="mt-1 truncate text-xs text-white/40" title={v.src.ledger}>{v.src.ledger}</div>
      </div>

      <div key={k("cost")} className={cn("rounded-3xl bg-peach text-ink shadow-(--glass-shadow)", TILE, flash)}>
        <div className="text-xs">What the fix costs</div>
        <div className="mt-2 flex flex-wrap items-end gap-x-5 gap-y-1">
          <div><div className="text-3xl font-light">{v.storageMb ?? "?"}<span className="text-base"> MB</span></div><div className="text-xs">on disk</div></div>
          <div><div className="text-3xl font-light">+{v.writeCostMs}<span className="text-base"> ms</span></div><div className="text-xs">per insert{v.twinTag && " (assumed per-index penalty unless replayed)"}, {writeShare(v.writeCostMs)}</div></div>
        </div>
        <div className="mt-1 text-xs">result {v.checksumMatch ? "identical" : "differs"}{v.live && `; checker ${v.llm.checker ?? "not run"}`}</div>
        <Source>storage: {v.src.twin}; write cost: {v.src.writeCost}; checksum: {v.src.checksum}</Source>
      </div>

      <div key={k("time")} className={cn("rounded-3xl bg-sky text-ink shadow-(--glass-shadow)", TILE, flash)}>
        <div className="flex items-center justify-between text-xs">
          Where the time goes
          <Link href="/stages/twin" className="inline-flex items-center gap-1 font-medium hover:underline">waterfall <ArrowRight className="size-3" /></Link>
        </div>
        <ul className="mt-2 space-y-1.5" aria-label={`measured times; ${v.src.twin}`}>
          {spans.map((s) => (
            <li key={s.id} className="text-xs">
              <div className="flex justify-between"><span>{s.label}</span><span className="font-mono">{s.dur} ms</span></div>
              <div className="h-1.5 rounded-full bg-white/60"><div className={cn("h-full origin-left rounded-full transition-transform duration-700 ease-out motion-reduce:transition-none", s.tone === "after" ? "bg-sky-ink" : "bg-ink")} style={{ transform: `scaleX(${(s.dur / most) * grown})` }} /></div>
            </li>
          ))}
          {!spans.length && <li className="text-xs">No measured time in this bundle</li>}
        </ul>
      </div>
    </Bento>
  );
}
