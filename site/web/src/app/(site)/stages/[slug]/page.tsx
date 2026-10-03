import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { StageSheet } from "@/components/playground/inspector";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { StageDetails } from "@/components/site/stage-details";
import { H1, H2, Page } from "@/components/site/prose";
import { RunBanner } from "@/components/viz/run-banner";
import { StageVisual } from "@/components/viz/stage-visuals";
import { STAGES, STAGE_COPY, type StageId } from "@/lib/stages";
import { cn } from "@/lib/utils";

export const dynamicParams = false;

export function generateStaticParams() {
  return STAGES.map((s) => ({ slug: s.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const s = STAGES.find((x) => x.id === slug);
  return s ? { title: `${s.title} | Tiresias`, description: STAGE_COPY[s.id].heading } : {};
}

const STATE_STYLE = {
  REAL: "border-accent/40 bg-accent-soft text-accent",
  SIMPLIFIED: "border-slate-300 bg-slate-100/80 text-slate-700",
  PLACEHOLDER: "border-slate-300 bg-slate-50/80 text-slate-700",
  MISSING: "border-signal/40 bg-signal-soft text-signal",
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
    <Page>
      <RunBanner className="mb-3" />
      <div className="mb-2 font-mono text-xs text-slate-500">Stage {i + 1} of {STAGES.length}</div>
      <H1>{c.heading}</H1>
      <ul className="mt-4 flex flex-wrap gap-2">
        {c.status.map((s) => (
          <li key={s.text} className="glass-subtle flex max-w-full items-start gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-700" title={s.text}>
            <span className={cn("shrink-0 rounded border px-1 font-mono text-xs", STATE_STYLE[s.state])}>{s.state}</span>
            {s.state !== "REAL" && <span className="[overflow-wrap:anywhere]">{s.text}</span>}
          </li>
        ))}
        {id === "gnn" && <li><Link href="/gnn" className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white hover:bg-slate-800">Explore the GNN <ArrowRight className="size-3.5" /></Link></li>}
      </ul>

      <div className="mt-6"><StageVisual id={id} /></div>

      <H2>Try it</H2>
      {id === "gateway" && <div className="mb-4"><HashingVisualizer /></div>}
      <div className="glass-strong max-w-3xl rounded-xl p-5"><StageSheet id={id} /></div>

      <H2>Details</H2>
      <StageDetails c={c} />

      <nav className="mt-8 flex justify-between gap-3 text-sm">
        {prev ? <Link href={`/stages/${prev.id}`} className="inline-flex items-center gap-1.5 text-slate-700 hover:text-slate-900"><ArrowLeft className="size-4" />{prev.title}</Link> : <span />}
        {next && <Link href={`/stages/${next.id}`} className="inline-flex items-center gap-1.5 text-slate-700 hover:text-slate-900">{next.title}<ArrowRight className="size-4" /></Link>}
      </nav>
    </Page>
  );
}
