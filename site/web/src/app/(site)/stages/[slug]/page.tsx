import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Minus, X } from "lucide-react";
import { StageSheet } from "@/components/playground/inspector";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { H1, H2, Lead } from "@/components/site/prose";
import { STAGES, STAGE_COPY, type StageId } from "@/lib/stages";
import { cn } from "@/lib/utils";

export const dynamicParams = false;

export function generateStaticParams() {
  return STAGES.map((s) => ({ slug: s.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const s = STAGES.find((x) => x.id === slug);
  return s ? { title: `${s.title} | Blind Tuner`, description: STAGE_COPY[s.id].heading } : {};
}

const STATE_STYLE = {
  REAL: "border-emerald-300 bg-emerald-50/80 text-emerald-800",
  SIMPLIFIED: "border-amber-300 bg-amber-50/80 text-amber-900",
  PLACEHOLDER: "border-slate-300 bg-slate-50/80 text-slate-700",
  MISSING: "border-red-300 bg-red-50/80 text-red-800",
};

export default async function StagePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const i = STAGES.findIndex((s) => s.id === slug);
  if (i < 0) notFound();
  const id = STAGES[i].id as StageId;
  const c = STAGE_COPY[id];
  const prev = STAGES[i - 1];
  const next = STAGES[i + 1];
  return (
    <article>
      <div className="mb-3 font-mono text-xs text-slate-600">Stage {i + 1} of {STAGES.length}: {STAGES[i].title}</div>
      <H1>{c.heading}</H1>
      <Lead>{c.lead}</Lead>
      <Link href="/playground" className="mt-4 inline-flex items-center gap-1 text-sm text-blue-700 underline">Replay this stage in the playground</Link>

      <H2>How it works</H2>
      <ol className="glass max-w-3xl space-y-2 rounded-xl p-5 text-sm leading-relaxed text-slate-700">
        {c.steps.map((s, n) => (
          <li key={n} className="flex gap-3"><span className="font-mono text-xs leading-6 text-slate-500">{n + 1}</span><span>{s}</span></li>
        ))}
      </ol>

      {c.sent && c.never && (
        <>
          <H2>What crosses to the AI side</H2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="glass rounded-xl p-5">
              <div className="mb-2 text-sm font-semibold text-slate-900">Sent</div>
              <ul className="space-y-1.5 text-sm text-slate-700">{c.sent.map((x) => <li key={x} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-emerald-600" />{x}</li>)}</ul>
            </div>
            <div className="glass rounded-xl p-5">
              <div className="mb-2 text-sm font-semibold text-slate-900">Never sent</div>
              <ul className="space-y-1.5 text-sm text-slate-700">{c.never.map((x) => <li key={x} className="flex gap-2"><X className="mt-0.5 size-4 shrink-0 text-red-600" />{x}</li>)}</ul>
            </div>
          </div>
        </>
      )}

      <H2>Measured</H2>
      <div className="glass overflow-x-auto rounded-xl">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs text-slate-600"><tr><th className="px-4 py-2 font-medium">Figure</th><th className="px-4 py-2 font-medium">Value</th><th className="px-4 py-2 font-medium">Source and assumption</th></tr></thead>
          <tbody>
            {c.figures.map((f) => (
              <tr key={f.label} className="border-t border-slate-200/70 align-top">
                <td className="px-4 py-2 text-slate-700">{f.label}</td>
                <td className="px-4 py-2 font-mono font-semibold tracking-tight text-slate-900">{f.value}</td>
                <td className="px-4 py-2 text-xs text-slate-600">{f.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <H2>Try it</H2>
      {id === "gateway" && <div className="mb-4"><HashingVisualizer /></div>}
      <div className="glass-strong max-w-3xl rounded-xl p-5"><StageSheet id={id} /></div>

      <H2>Built, simplified or missing</H2>
      <ul className="max-w-3xl space-y-2">
        {c.status.map((s) => (
          <li key={s.text} className="glass flex items-start gap-3 rounded-xl p-3 text-sm text-slate-700">
            <span className={cn("shrink-0 rounded-md border px-1.5 py-0.5 font-mono text-[11px]", STATE_STYLE[s.state])}>{s.state}</span>
            {s.text}
          </li>
        ))}
      </ul>

      <H2>Failures and fixes</H2>
      <div className="glass overflow-x-auto rounded-xl">
        <table className="w-full min-w-[480px] text-left text-sm">
          <thead className="text-xs text-slate-600"><tr><th className="px-4 py-2 font-medium">Failure</th><th className="px-4 py-2 font-medium">Fix</th></tr></thead>
          <tbody>
            {c.failures.map(([f, x]) => (
              <tr key={f} className="border-t border-slate-200/70 align-top"><td className="px-4 py-2 text-slate-700">{f}</td><td className="px-4 py-2 text-slate-700">{x}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-600"><Minus className="size-3" /> Sources: {c.sources}</p>

      <nav className="mt-10 grid gap-3 sm:grid-cols-2">
        {prev ? (
          <Link href={`/stages/${prev.id}`} className="glass flex items-center gap-2 rounded-xl p-4 text-sm text-slate-900 hover:bg-white/90"><ArrowLeft className="size-4" /> Stage {i}: {prev.title}</Link>
        ) : <span />}
        {next && (
          <Link href={`/stages/${next.id}`} className="glass flex items-center justify-end gap-2 rounded-xl p-4 text-sm text-slate-900 hover:bg-white/90">Stage {i + 2}: {next.title} <ArrowRight className="size-4" /></Link>
        )}
      </nav>
    </article>
  );
}
