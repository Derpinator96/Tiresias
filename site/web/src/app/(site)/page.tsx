import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { H1, H2, Lead, P } from "@/components/site/prose";
import { run } from "@/lib/facts";
import { STAGES, STAGE_SUMMARY } from "@/lib/stages";

const HEADLINE = [
  { label: "Q1 on the twin", value: `${run.twin.before_ms.toFixed(1)} to ${run.twin.after_ms.toFixed(1)} ms`, note: `${run.twin.speedup_pct}% faster, median of ${run.twin.runs} runs` },
  { label: "canary hits", value: `${run.privacy.canary_hits} of ${run.privacy.canaries_planted}`, note: `across ${run.privacy.payloads} outbound payloads` },
  { label: "index cost", value: `${run.twin.storage_mb} MB`, note: "measured on the twin's disk" },
  { label: "LLM numbers checked", value: String(run.llm.numbers_checked), note: `in ${run.llm.tool_calls} tool calls, ${run.llm.model}` },
];

const BOUNDARY: [string, string, string][] = [
  ["Values", "emails, sums, dates, filter values", "No. Replaced by ?; every payload is scanned for planted canary values before it leaves."],
  ["Names", "table and column names", "No. HMAC-SHA256 codes such as t_7a3f91c2 (illustrative), computed with a key that stays in the gateway."],
  ["Statistics value lists", "most common values, histogram bounds", "No. Replaced by one skew score from 0 to 1."],
  ["The DBA's question", "\"why is this report slow?\"", "No. Mapped to query template codes inside the gateway."],
  ["Query shape", "which column uses =, joins, grouping", "Yes. The fix depends on it."],
  ["Sizes", "row counts, table and index sizes", "Yes, rounded to 2 significant figures."],
  ["Column roles", "primary key, indexed, used in a range", "Yes, as role flags."],
];

export default function Home() {
  return (
    <>
      <H1>Blind Tuner finds fixes for slow PostgreSQL queries while its AI sees only hashed metadata</H1>
      <Lead>
        A gateway inside the database owner&apos;s network replaces every table and column name with a keyed hash and strips every value before anything reaches the AI. The AI proposes indexes and rewrites from that metadata. Each proposal is measured on a synthetic copy of the database before a DBA sees it.
      </Lead>
      <div className="mt-6 flex flex-wrap gap-2">
        <Link href="/playground" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800">
          Replay the pipeline <ArrowRight className="size-4" />
        </Link>
        <Link href="/hashing" className="glass-subtle inline-flex h-9 items-center rounded-lg px-3 text-sm font-medium text-slate-900 hover:bg-white/80">Hash your own SQL</Link>
        <Link href="/ask" className="glass-subtle inline-flex h-9 items-center rounded-lg px-3 text-sm font-medium text-slate-900 hover:bg-white/80">See a DBA question answered</Link>
      </div>

      <H2>Measured in {run.run_id}</H2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {HEADLINE.map((h) => (
          <div key={h.label} className="glass rounded-xl p-4">
            <div className="text-xs text-slate-600">{h.label}</div>
            <div className="mt-1 font-mono text-xl font-semibold tracking-tight text-slate-900">{h.value}</div>
            <div className="mt-1 text-xs text-slate-600">{h.note}</div>
          </div>
        ))}
      </div>
      <P>
        Run {run.run_id} finished {run.finished_at} on our own synthetic retail database ({run.dataset.hero_table_rows.toLocaleString("en-US")} rows in the hero table), on one machine under load. These figures do not predict results on another database.
      </P>

      <H2>The pipeline has eight stages, each with its own page</H2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STAGES.map((s, i) => (
          <Link key={s.id} href={`/stages/${s.id}`} className="group">
            <Card className="h-full transition-colors group-hover:bg-white/90">
              <CardHeader>
                <div className="font-mono text-[11px] text-slate-500">Stage {i + 1}</div>
                <CardTitle>{s.title}</CardTitle>
                <CardDescription className="text-slate-600">{STAGE_SUMMARY[s.id]}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>

      <H2>What crosses the boundary and what does not</H2>
      <div className="glass overflow-x-auto rounded-xl">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr><th className="px-4 py-2 font-medium">Category</th><th className="px-4 py-2 font-medium">Example</th><th className="px-4 py-2 font-medium">Sent to the AI?</th></tr>
          </thead>
          <tbody>
            {BOUNDARY.map(([c, e, s]) => (
              <tr key={c} className="border-t border-slate-200/70 align-top">
                <th scope="row" className="px-4 py-2 font-medium text-slate-900">{c}</th>
                <td className="px-4 py-2 text-slate-700">{e}</td>
                <td className="px-4 py-2 text-slate-700">{s}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <P>
        The shape of the schema (how many tables, how they link) still reaches the AI and can hint at the kind of business. Blind Tuner claims that no raw value or real name crosses the boundary, not that nothing does.
      </P>
    </>
  );
}
