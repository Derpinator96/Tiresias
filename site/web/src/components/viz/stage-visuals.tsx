"use client";
// One visual block per stage. Nothing here holds a number: figures come from the run view
// (the current bundle, or the run record) or from data/measurements.json, and charts recompute
// when either changes. (tests/spans.test.mjs fails if a literal number appears in this file.)
import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { BigNumber, ChartCard, Flow, HBars, LineChart, PartBar, SERIES } from "@/components/viz/charts";
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

function Source() {
  const v = useView();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title={v.meanBefore === null ? "The template's mean time is not in the bundle" : `${v.live ? v.templateId : "Q1"} is ${v.meanBefore > v.slowThresholdMs ? "slower" : "not slower"} than the slow-query threshold`} caption={`${v.src.prod}; ${v.src.threshold}`}>
        <HBars unit=" ms" bars={v.meanBefore === null ? [] : [{ label: `${v.live ? v.templateId : "Q1"} mean, pg-prod`, value: v.meanBefore, color: SERIES.orange, note: "before" }]} refLine={{ value: v.slowThresholdMs, label: `slow at ${v.slowThresholdMs} ms` }} />
      </ChartCard>
      <ChartCard title="One value holds a third of the rows" caption={m.skew.source}>
        <PartBar unit="%" total={m.skew.total_percent} parts={[{ label: m.skew.label, value: m.skew.percent, color: SERIES.blue }, { label: "all other values", value: m.skew.rest_percent, color: SERIES.orange }]} />
      </ChartCard>
    </div>
  );
}

function Gateway() {
  const v = useView();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title="Names become codes, values become ?" caption="illustrative code; the real key never leaves the gateway" className="md:col-span-2">
        <div className="space-y-2">
          <Flow steps={[{ label: "table name" }, { label: "HMAC-SHA256", sub: "secret key" }, { label: `first ${CONFIG.hexChars} hex` }, { label: "AI sees", sub: CODE.table, tone: "ai" }]} />
          <Flow steps={[{ label: "value" }, { label: "stripped" }, { label: "AI sees", sub: "?", tone: "ai" }]} />
        </div>
      </ChartCard>
      <ChartCard title={`Where the ${v.payloads} payloads went`} caption={v.src.ledger}>
        {v.llmPayloads === null
          ? <PartBar parts={[{ label: "ai service and LLM (split not in the bundle)", value: v.payloads, color: SERIES.blue }]} />
          : <PartBar parts={[{ label: "ai service", value: v.payloads - v.llmPayloads, color: SERIES.blue }, { label: "LLM", value: v.llmPayloads, color: SERIES.orange }]} />}
      </ChartCard>
      <ChartCard title="Canary leaks" caption={`${v.canariesPlanted} planted canaries scanned per payload; ${runLine(v)}`}>
        <div className="flex items-center gap-3">
          <ShieldCheck className="size-8 text-accent" />
          <BigNumber value={`${v.canaryHits} of ${v.canariesPlanted}`} label="canaries leaked" tone={v.canaryHits ? "default" : "good"} />
        </div>
      </ChartCard>
    </div>
  );
}

function Miner() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title="Drift: the workload mix changed" caption={m.drift.source}>
        <LineChart yMax={maxOf(m.drift.windows.map((w) => w.distance)) * m.drift.y_headroom} points={m.drift.windows.map((w) => ({ label: w.label, value: w.distance }))} threshold={{ value: m.drift.threshold, label: `trigger ${m.drift.threshold}` }} />
      </ChartCard>
      <ChartCard title="Basket to candidate index" caption="illustrative codes">
        <Flow steps={[{ label: "slow query", sub: `${CODE.eq}:EQ` }, { label: "same query", sub: `${CODE.range}:RANGE` }, { label: "FP-Growth", sub: "weighted by time" }, { label: "candidate", sub: "EQ first, then RANGE", tone: "ai" }]} />
      </ChartCard>
    </div>
  );
}

function Gnn() {
  const v = useView();
  const [metric, setMetric] = useState(m.gnn.metrics[0].id);
  const key = metric as "median" | "p95";
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title="Prediction error by model" caption={m.gnn.source}>
        <div className="glass-subtle mb-2 flex w-fit rounded-full p-0.5 text-xs">
          {m.gnn.metrics.map((x) => (
            <button key={x.id} onClick={() => setMetric(x.id)} aria-pressed={metric === x.id} className={`h-6 rounded-full px-2.5 ${metric === x.id ? "bg-ink text-white" : "text-slate-600"}`}>{x.label}</button>
          ))}
        </div>
        <HBars digits={3} bars={m.gnn.models.map((x) => ({ label: x.label, value: x[key], color: slot(x.slot) }))} />
      </ChartCard>
      <ChartCard title="What serves today: predicted time" caption={v.src.predicted}>
        <HBars unit=" ms" bars={[{ label: "before", value: v.predictedBefore ?? 0, color: SERIES.orange }, { label: "with the chosen actions", value: v.predictedAfter ?? 0, color: SERIES.blue }]} />
      </ChartCard>
    </div>
  );
}

function Rl() {
  const v = useView();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title="Search loop" caption={`config.yaml rl.*: alpha ${CONFIG.alpha}, gamma ${CONFIG.gamma}`} className="md:col-span-2">
        <Flow steps={[{ label: "mined candidates" }, { label: "Q-learning", sub: `${CONFIG.episodes} episodes`, tone: "ai" }, { label: "top configs" }, { label: "twin measures each" }, { label: "best measured wins", tone: "check" }]} />
      </ChartCard>
      {v.live ? (
        <ChartCard title={`${v.actions.length} chosen ${v.actions.length === 1 ? "action" : "actions"}`} caption={`${v.src.search}; ${v.searchLabel}`}>
          <ul className="space-y-1 font-mono text-xs text-slate-800">
            {v.actions.map((a) => <li key={a}>{a}</li>)}
            {v.actions.length === 0 && <li className="text-slate-400">none</li>}
          </ul>
        </ChartCard>
      ) : (
        <ChartCard title="Q1, predicted by the search" caption={`${m.rl.source}; ${m.rl.episodes_note}`}>
          <HBars unit=" ms" bars={[{ label: "before", value: m.rl.q1_predicted_ms.before, color: SERIES.orange }, { label: "with the index", value: m.rl.q1_predicted_ms.after, color: SERIES.blue }]} />
        </ChartCard>
      )}
      <ChartCard title="Q3 with monthly partitions, measured on the twin" caption={m.rl.q3_source}>
        <HBars unit=" ms" bars={[{ label: "before", value: m.rl.q3_partition_twin_ms.before, color: SERIES.orange }, { label: "partitioned", value: m.rl.q3_partition_twin_ms.after, color: SERIES.blue }]} />
      </ChartCard>
    </div>
  );
}

function Llm() {
  const v = useView();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title="One question, start to answer" className="md:col-span-2">
        <Flow steps={[{ label: "DBA question" }, { label: "gateway", sub: "question to codes" }, { label: "LLM + tools", sub: "codes only", tone: "ai" }, { label: "number checker", tone: "check" }, { label: "gateway", sub: "codes to names" }, { label: "DBA reads answer" }]} />
      </ChartCard>
      <ChartCard title="Tool calls used" caption={`${v.src.llm}; ${m.llm.source}`}>
        <PartBar total={m.llm.max_tool_calls} parts={[{ label: "calls", value: v.llm.toolCalls ?? 0, color: SERIES.blue }]} />
      </ChartCard>
      <ChartCard title="Numbers in the answer" caption={`${v.src.llm}, ${v.llm.model}`}>
        {v.live
          ? <BigNumber value={v.llm.checker ?? "not run"} label="number checker" tone={v.llm.checker === "ok" ? "good" : "default"} />
          : <BigNumber value={`${v.llm.numbersChecked} checked`} label="all matched tool results" tone="good" />}
      </ChartCard>
    </div>
  );
}

function Twin() {
  const v = useView();
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <ChartCard title={v.speedupPct === null ? "No twin measurement in this bundle" : `${v.live ? v.templateId : "Q1"}: ${v.speedupPct.toFixed(1)}% faster on the twin`} caption={`${v.src.twin}; spans laid end to end, not concurrent`} className="md:col-span-2">
        <Waterfall spans={q1Spans(v)} />
      </ChartCard>
      <ChartCard title="Twin fidelity" caption={m.fidelity.source}>
        <HBars digits={3} max={m.fidelity.exact} refLine={{ value: m.fidelity.exact, label: "exact" }} bars={m.fidelity.queries.map((q) => ({ label: q.label, value: q.value, color: SERIES.blue }))} />
      </ChartCard>
      <ChartCard title="Cost of the change" caption={`storage: ${v.src.twin}; write cost: ${v.src.writeCost}; checksum: ${v.src.checksum}`}>
        <div className="flex flex-wrap gap-8">
          <BigNumber value={fmt(v.storageMb, " MB")} label="on disk" />
          <BigNumber value={`+${v.writeCostMs} ms`} label="per insert" />
          <BigNumber value={v.checksumMatch ? "match" : "differs"} label="result checksum" tone="good" />
        </div>
      </ChartCard>
    </div>
  );
}

function Dba() {
  return (
    <ChartCard title="From approval to production" caption={m.approve.source}>
      <Flow steps={[{ label: "approve", sub: "files with real names" }, { label: "baseline" }, { label: "migration.sql", sub: "CONCURRENTLY" }, { label: "check", sub: `${m.approve.check_minutes} min` }, { label: `median worse by ${m.approve.rollback_worse_by_pct}%?`, tone: "check" }, { label: "rollback.sql" }]} />
    </ChartCard>
  );
}

const VISUALS: Record<StageId, () => React.ReactElement> = { source: Source, gateway: Gateway, miner: Miner, gnn: Gnn, rl: Rl, llm: Llm, twin: Twin, dba: Dba };

export function StageVisual({ id }: { id: StageId }) {
  const V = VISUALS[id];
  return <V />;
}
