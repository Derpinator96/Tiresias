"use client";
import { Check, X } from "lucide-react";
import { useContextStore } from "@/lib/context";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import type { StageCopy, StageId } from "@/lib/stages";

/** Pulsing lime pill beside the H1 while the live question is at this stage. */
export function RunningNow({ id }: { id: StageId }) {
  const on = useContextStore((s) => s.running?.stage === id);
  if (!on) return null;
  return (
    <span className="pill inline-flex h-7 items-center gap-1.5 bg-lime px-3 text-xs font-medium text-ink">
      <span className="size-2 animate-pulse rounded-full bg-ink motion-reduce:animate-none" aria-hidden /> running now
    </span>
  );
}

/** The long text of a stage page, collapsed by default. */
export function StageDetails({ c }: { c: StageCopy }) {
  return (
    <Accordion className="glass px-5">
      <AccordionItem value="how">
        <AccordionTrigger>How it works</AccordionTrigger>
        <AccordionContent>
          <ol className="space-y-1.5 text-slate-700">
            {c.steps.map((s, n) => <li key={n} className="flex gap-3"><span className="font-mono text-xs leading-5 text-slate-500">{n + 1}</span><span>{s}</span></li>)}
          </ol>
        </AccordionContent>
      </AccordionItem>
      {c.sent && c.never && (
        <AccordionItem value="boundary">
          <AccordionTrigger>What crosses to the AI side</AccordionTrigger>
          <AccordionContent>
            <div className="grid gap-4 sm:grid-cols-2">
              <ul className="space-y-1 text-slate-700">{c.sent.map((x) => <li key={x} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-slate-700" />{x}</li>)}</ul>
              <ul className="space-y-1 text-slate-700">{c.never.map((x) => <li key={x} className="flex gap-2"><X className="mt-0.5 size-4 shrink-0 text-slate-400" />{x}</li>)}</ul>
            </div>
          </AccordionContent>
        </AccordionItem>
      )}
      <AccordionItem value="figures">
        <AccordionTrigger>Every figure and its source</AccordionTrigger>
        <AccordionContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-left">
              <tbody>
                {c.figures.map((f) => (
                  <tr key={f.label} className="align-top even:bg-slate-50">
                    <td className="py-1.5 pr-3 text-slate-700">{f.label}</td>
                    <td className="py-1.5 pr-3 font-mono font-semibold text-slate-900">{f.value}</td>
                    <td className="py-1.5 text-xs text-slate-600">{f.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="failures">
        <AccordionTrigger>Failures and fixes</AccordionTrigger>
        <AccordionContent>
          <ul className="space-y-1.5 text-slate-700">
            {c.failures.map(([f, x]) => <li key={f}><span className="text-slate-900">{f}</span>: {x}</li>)}
          </ul>
          <p className="mt-3 text-xs text-slate-600">Sources: {c.sources}</p>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
