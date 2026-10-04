import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { StageSheet } from "@/components/playground/inspector";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { StageDetails } from "@/components/site/stage-details";
import { H1, Page } from "@/components/site/prose";
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

// Monochrome state tags: weight and shade carry the state, not colour.
const STATE_STYLE = {
  REAL: "bg-ink text-white",
  SIMPLIFIED: "bg-slate-200 text-slate-800",
  PLACEHOLDER: "bg-slate-100 text-slate-600",
  MISSING: "bg-slate-300 text-slate-900",
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
      <H1>{c.heading}</H1>
      <ul className="mt-4 flex flex-wrap gap-2">
        {c.status.map((s) => (
          <li key={s.text} className="flex max-w-full items-center gap-2 rounded-full bg-white py-1 pl-1 pr-3 text-xs text-slate-700 shadow-(--glass-shadow)" title={s.text}>
            <span className={cn("shrink-0 rounded-full px-2 py-0.5 font-mono text-xs", STATE_STYLE[s.state])}>{s.state}</span>
            {s.state !== "REAL" && <span className="[overflow-wrap:anywhere]">{s.text}</span>}
          </li>
        ))}
        {id === "gnn" && <li><Link href="/gnn" className="inline-flex h-7 items-center gap-1 rounded-full bg-ink px-3 text-xs text-white hover:bg-slate-800">Explore the GNN <ArrowRight className="size-3.5" /></Link></li>}
      </ul>

      <div className="mt-6"><StageVisual id={id} /></div>

      {id === "gateway" && <div className="mt-6"><HashingVisualizer /></div>}
      <div className="glass-strong mt-6 max-w-3xl rounded-xl p-5"><StageSheet id={id} /></div>
      <div className="mt-4"><StageDetails c={c} /></div>

      <nav className="mt-8 flex justify-between gap-3 text-sm">
        {prev ? <Link href={`/stages/${prev.id}`} className="inline-flex items-center gap-1.5 text-slate-700 hover:text-slate-900"><ArrowLeft className="size-4" />{prev.title}</Link> : <span />}
        {next && <Link href={`/stages/${next.id}`} className="inline-flex items-center gap-1.5 text-slate-700 hover:text-slate-900">{next.title}<ArrowRight className="size-4" /></Link>}
      </nav>
    </Page>
  );
}
