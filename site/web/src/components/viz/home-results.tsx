"use client";
// The home page's results section, from the run view (the current bundle, or the run record).
// Holds no literal numbers (tests/spans.test.mjs).
import { ShieldCheck } from "lucide-react";
import { BigNumber, ChartCard, PartBar, SERIES } from "@/components/viz/charts";
import { RunBanner } from "@/components/viz/run-banner";
import { Waterfall } from "@/components/viz/waterfall";
import { H2 } from "@/components/site/prose";
import { q1Spans } from "@/lib/spans";
import { useView } from "@/lib/view";

export function HomeResults() {
  const v = useView();
  const what = v.live ? v.templateId : "Q1";
  const line = v.live ? `bundle ${v.id}` : `${v.id}, synthetic data, ${v.heroRows?.toLocaleString("en-US")} rows, one machine`;
  return (
    <>
      <H2>Results of {v.id}</H2>
      <RunBanner className="mb-3" />
      <div className="grid gap-3 md:grid-cols-2">
        <ChartCard title={v.speedupPct === null ? "No twin measurement in this bundle" : `${what}: ${v.speedupPct.toFixed(1)}% faster with ${!v.live ? "one index" : v.actions.length === 1 ? v.actions[0] : `${v.actions.length} actions`}`} caption={`${v.src.twin}; spans laid end to end, not concurrent`} className="md:col-span-2">
          <Waterfall spans={q1Spans(v)} />
        </ChartCard>
        <ChartCard title={v.canaryHits ? "Canary hits" : "Nothing leaked"} caption={`${v.canariesPlanted} planted canaries scanned per payload; ${line}`}>
          <div className="flex items-center gap-3">
            <ShieldCheck className="size-8 text-emerald-600" />
            <BigNumber value={`${v.canaryHits} of ${v.canariesPlanted}`} label={`canaries found in ${v.payloads} payloads`} tone={v.canaryHits ? "default" : "good"} />
          </div>
          <div className="mt-4">
            {v.llmPayloads === null
              ? <PartBar parts={[{ label: "to the ai service and the LLM (split not in the bundle)", value: v.payloads, color: SERIES.blue }]} />
              : <PartBar parts={[{ label: "to the ai service", value: v.payloads - v.llmPayloads, color: SERIES.blue }, { label: "to the LLM", value: v.llmPayloads, color: SERIES.orange }]} />}
          </div>
        </ChartCard>
        <ChartCard title="What the fix costs" caption={`storage: ${v.src.twin}; write cost: ${v.src.writeCost}; checksum: ${v.src.checksum}`} className="md:col-span-2">
          <div className="flex flex-wrap gap-10">
            <BigNumber value={v.storageMb === null ? "not in bundle" : `${v.storageMb} MB`} label="index on disk" />
            <BigNumber value={`+${v.writeCostMs} ms`} label="per insert" />
            <BigNumber value={v.checksumMatch ? "identical" : "differs"} label="query result" tone="good" />
            {v.live
              ? <BigNumber value={v.llm.checker ?? "not run"} label="LLM number checker" tone={v.llm.checker === "ok" ? "good" : "default"} />
              : <BigNumber value={String(v.llm.numbersChecked)} label="LLM numbers checked" />}
          </div>
        </ChartCard>
      </div>
    </>
  );
}
