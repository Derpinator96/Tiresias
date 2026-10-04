"use client";
// One visual block per stage. Nothing here holds a number: figures come from the run view
// (the current bundle, or the run record) or from data/measurements.json, and charts recompute
// when either changes. (tests/spans.test.mjs fails if a literal number appears in this file.)
import { useState } from "react";
import { Bento, BigNumber, ChartCard, Flow, Gauge, HBars, LineChart, PartBar, SERIES } from "@/components/viz/charts";
import { Waterfall } from "@/components/viz/waterfall";
import { CODE, CONFIG } from "@/lib/facts";
import type { RunView } from "@/lib/run-view";
import { q1Spans } from "@/lib/spans";
import type { StageId } from "@/lib/stages";
import { useView } from "@/lib/view";
import m from "@/data/measurements.json";

const runLine = (v: RunView) => (v.live ? `bundle ${v.id}` : `${v.id}, synthetic data, ${v.heroRows?.toLocaleString("en-US")} rows`);
const NA = "not in bundle";
const fmt = (x: number | null, unit = " ms") => (x === null ? NA : `${x}${unit}`);
const slot = (s: string) => SERIES[s as keyof typeof SERIES];
const maxOf = (xs: number[]) => Math.max(...xs);
// Bento spans: two or three tiles per row.
const S12 = "md:col-span-12", S8 = "md:col-span-8", S6 = "md:col-span-6", S4 = "md:col-span-4", S3 = "md:col-span-3";

function Source() {
  const v = useView();
  return (
    <>
      <ChartCard title={v.meanBefore === null ? "The template's mean time is not in the bundle" : `${v.live ? v.templateId : "Q1"} is ${v.meanBefore > v.slowThresholdMs ? "slower" : "not slower"} than the slow-query threshold`} caption={`${v.src.prod}; ${v.src.threshold}`} className={S6}>
        <HBars unit=" ms" bars={v.meanBefore === null ? [] : [{ label: `${v.live ? v.templateId : "Q1"} mean, pg-prod`, value: v.meanBefore, color: SERIES.orange, note: "before" }]} refLine={{ value: v.slowThresholdMs, label: `slow at ${v.slowThresholdMs} ms` }} />
      </ChartCard>
      <ChartCard title="One value holds a third of the rows" caption={m.skew.source} className={S6}>
        <PartBar unit="%" total={m.skew.total_percent} parts={[{ label: m.skew.label, value: m.skew.percent, color: SERIES.blue }, { label: "all other values", value: m.skew.rest_percent, color: SERIES.orange }]} />
      </ChartCard>
    </>
  );
}

function Gateway() {
  const v = useView();
  return (
    <>
      <ChartCard title="Names become codes, values become ?" caption="illustrative code; the real key never leaves the gateway" className={S6}>
        <div className="space-y-2">
          <Flow steps={[{ label: "table name" }, { label: "HMAC-SHA256", sub: "secret key" }, { label: `first ${CONFIG.hexChars} hex` }, { label: "AI sees", sub: CODE.table, tone: "ai" }]} />
          <Flow steps={[{ label: "value" }, { label: "stripped" }, { label: "AI sees", sub: "?", tone: "ai" }]} />
        </div>
      </ChartCard>
      <ChartCard title={`Where the ${v.payloads} payloads went`} caption={v.src.ledger} className={S3}>
        {v.llmPayloads === null
          ? <PartBar parts={[{ label: "ai service and LLM (split not in the bundle)", value: v.payloads, color: SERIES.blue }]} />
          : <PartBar parts={[{ label: "ai service", value: v.payloads - v.llmPayloads, color: SERIES.blue }, { label: "LLM", value: v.llmPayloads, color: SERIES.orange }]} />}
      </ChartCard>
      <ChartCard title="Canary leaks" caption={`${v.canariesPlanted} planted canaries scanned per payload; ${runLine(v)}`} className={S3}>
        <Gauge value={v.canaryHits} max={v.canariesPlanted} unit={` of ${v.canariesPlanted}`} label="canaries leaked" />
      </ChartCard>
    </>
  );
}

function Miner() {
  return (
    <>
      <ChartCard title="Drift: the workload mix changed" caption={m.drift.source} className={S6}>
        <LineChart yMax={maxOf(m.drift.windows.map((w) => w.distance)) * m.drift.y_headroom} points={m.drift.windows.map((w) => ({ label: w.label, value: w.distance }))} threshold={{ value: m.drift.threshold, label: `trigger ${m.drift.threshold}` }} />
      </ChartCard>
      <ChartCard title="Basket to candidate index" caption="illustrative codes" className={S6}>
        <Flow steps={[{ label: "slow query", sub: `${CODE.eq}:EQ` }, { label: "same query", sub: `${CODE.range}:RANGE` }, { label: "FP-Growth", sub: "weighted by time" }, { label: "candidate", sub: "EQ first, then RANGE", tone: "ai" }]} />
      </ChartCard>
    </>
  );
}

function Gnn() {
  const v = useView();
  const [metric, setMetric] = useState(m.gnn.metrics[0].id);
  const key = metric as "median" | "p95";
  const gnn = m.gnn.models[0], pg = m.gnn.models.find((x) => x.label === "Postgres")!;
  return (
    <>
      <ChartCard title="Prediction error by model" caption={m.gnn.source} className={S4}>
        <div className="glass-subtle mb-2 flex w-fit rounded-full p-0.5 text-xs">
          {m.gnn.metrics.map((x) => (
            <button key={x.id} onClick={() => setMetric(x.id)} aria-pressed={metric === x.id} className={`h-6 rounded-full px-2.5 ${metric === x.id ? "bg-ink text-white" : "text-slate-600"}`}>{x.label}</button>
          ))}
        </div>
        <HBars digits={3} bars={m.gnn.models.map((x) => ({ label: x.label, value: x[key], color: slot(x.slot) }))} />
      </ChartCard>
      <ChartCard title="What serves today: predicted time" caption={v.src.predicted} className={S4}>
        <HBars unit=" ms" bars={[{ label: "before", value: v.predictedBefore ?? 0, color: SERIES.orange }, { label: "with the chosen actions", value: v.predictedAfter ?? 0, color: SERIES.blue }]} />
      </ChartCard>
      <ChartCard title={`${gnn.label} vs Postgres`} caption={`${m.gnn.source}; full dial = Postgres q-error`} className={S4}>
        <Gauge value={gnn[key]} max={pg[key]} digits={2} label={`${gnn.label} q-error, Postgres ${pg[key]}`} />
      </ChartCard>
    </>
  );
}

function Rl() {
  const v = useView();
  return (
    <>
      <ChartCard title="Search loop" caption={`config.yaml rl.*: alpha ${CONFIG.alpha}, gamma ${CONFIG.gamma}`} className={S12}>
        <Flow steps={[{ label: "mined candidates" }, { label: "Q-learning", sub: `${CONFIG.episodes} episodes`, tone: "ai" }, { label: "top configs" }, { label: "twin measures each" }, { label: "best measured wins", tone: "check" }]} />
      </ChartCard>
      {v.live ? (
        <ChartCard title={`${v.actions.length} chosen ${v.actions.length === 1 ? "action" : "actions"}`} caption={`${v.src.search}; ${v.searchLabel}`} className={S6}>
          <ul className="space-y-1 font-mono text-xs text-slate-800">
            {v.actions.map((a) => <li key={a}>{a}</li>)}
            {v.actions.length === 0 && <li className="text-slate-400">none</li>}
          </ul>
        </ChartCard>
      ) : (
        <ChartCard title="Q1, predicted by the search" caption={`${m.rl.source}; ${m.rl.episodes_note}`} className={S6}>
          <HBars unit=" ms" bars={[{ label: "before", value: m.rl.q1_predicted_ms.before, color: SERIES.orange }, { label: "with the index", value: m.rl.q1_predicted_ms.after, color: SERIES.blue }]} />
        </ChartCard>
      )}
      <ChartCard title="Q3 with monthly partitions, measured on the twin" caption={m.rl.q3_source} className={S6}>
        <HBars unit=" ms" bars={[{ label: "before", value: m.rl.q3_partition_twin_ms.before, color: SERIES.orange }, { label: "partitioned", value: m.rl.q3_partition_twin_ms.after, color: SERIES.blue }]} />
      </ChartCard>
    </>
  );
}

function Llm() {
  const v = useView();
  return (
    <>
      <ChartCard title="One question, start to answer" className={S6}>
        <Flow steps={[{ label: "DBA question" }, { label: "gateway", sub: "question to codes" }, { label: "LLM + tools", sub: "codes only", tone: "ai" }, { label: "number checker", tone: "check" }, { label: "gateway", sub: "codes to names" }, { label: "DBA reads answer" }]} />
      </ChartCard>
      <ChartCard title="Tool calls used" caption={`${v.src.llm}; ${m.llm.source}`} className={S3}>
        {v.llm.toolCalls === null
          ? <BigNumber value={NA} label="tool calls" />
          : <Gauge value={v.llm.toolCalls} max={m.llm.max_tool_calls} unit={` of ${m.llm.max_tool_calls}`} label="tool calls, limit from config" />}
      </ChartCard>
      <ChartCard title="Numbers in the answer" caption={`${v.src.llm}, ${v.llm.model}`} className={S3}>
        {v.live || v.llm.numbersChecked === null
          ? <BigNumber value={v.llm.checker ?? "not run"} label="number checker" tone={v.llm.checker === "ok" ? "good" : "default"} />
          : <Gauge value={v.llm.numbersChecked} max={v.llm.numbersChecked} unit={` of ${v.llm.numbersChecked}`} label="matched tool results" />}
      </ChartCard>
    </>
  );
}

function Twin() {
  const v = useView();
  return (
    <>
      <ChartCard title={v.speedupPct === null ? "No twin measurement in this bundle" : `${v.live ? v.templateId : "Q1"}: ${v.speedupPct.toFixed(1)}% faster on the twin`} caption={`${v.src.twin}; spans laid end to end, not concurrent`} className={S8}>
        <Waterfall spans={q1Spans(v)} />
      </ChartCard>
      <ChartCard title="Speedup on the twin" caption={`${v.src.twin}; median of ${v.runs ?? "?"} runs`} className={S4}>
        {v.speedupPct === null ? <BigNumber value={NA} label="speedup" /> : <Gauge value={v.speedupPct} digits={1} unit="%" label="faster on the twin" />}
      </ChartCard>
      <ChartCard title="Twin fidelity" caption={m.fidelity.source} className={S6}>
        <HBars digits={3} max={m.fidelity.exact} refLine={{ value: m.fidelity.exact, label: "exact" }} bars={m.fidelity.queries.map((q) => ({ label: q.label, value: q.value, color: SERIES.blue }))} />
      </ChartCard>
      <ChartCard title="Cost of the change" caption={`storage: ${v.src.twin}; write cost: ${v.src.writeCost}; checksum: ${v.src.checksum}`} className={S6}>
        <div className="flex flex-wrap gap-8">
          <BigNumber value={fmt(v.storageMb, " MB")} label="on disk" />
          <BigNumber value={`+${v.writeCostMs} ms`} label="per insert" />
          <BigNumber value={v.checksumMatch ? "match" : "differs"} label="result checksum" tone="good" />
        </div>
      </ChartCard>
    </>
  );
}

function Dba() {
  return (
    <ChartCard title="From approval to production" caption={m.approve.source} className={S12}>
      <Flow steps={[{ label: "approve", sub: "files with real names" }, { label: "baseline" }, { label: "migration.sql", sub: "CONCURRENTLY" }, { label: "check", sub: `${m.approve.check_minutes} min` }, { label: `median worse by ${m.approve.rollback_worse_by_pct}%?`, tone: "check" }, { label: "rollback.sql" }]} />
    </ChartCard>
  );
}

const VISUALS: Record<StageId, () => React.ReactElement> = { source: Source, gateway: Gateway, miner: Miner, gnn: Gnn, rl: Rl, llm: Llm, twin: Twin, dba: Dba };

export function StageVisual({ id }: { id: StageId }) {
  const V = VISUALS[id];
  // small gauges on stage pages: cap the dial width and its number size
  return <Bento className="[&_div[role=img]]:max-w-[160px] [&_div[role=img]_.tracking-tight]:text-2xl!"><V /></Bento>;
}
