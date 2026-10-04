import Link from "next/link";
import { ArrowRight, Lock } from "lucide-react";
import { STAGES, STAGE_ICON, type StageId } from "@/lib/stages";
import { cn } from "@/lib/utils";

const ZONES: { label: string; sub: string; ids: StageId[]; ai?: boolean }[] = [
  { label: "Private network", sub: "real names and data", ids: ["source", "gateway"] },
  { label: "AI zone", sub: "hashed codes only", ids: ["miner", "gnn", "rl", "llm"], ai: true },
  { label: "Private network", sub: "measured, then approved", ids: ["twin", "dba"] },
];

/** The 8 stages across the trust boundary; every node links to its page. Monochrome: the zones are off-white panels. */
export function PipelineMap() {
  return (
    <div className="grid items-stretch gap-2 md:grid-cols-[1fr_auto_1.6fr_auto_1fr]">
      {ZONES.map((z, zi) => (
        <div key={zi} className="contents">
          {zi > 0 && (
            <div className="flex items-center justify-center gap-1 py-1 text-slate-400 md:flex-col">
              <Lock className="size-3.5" aria-hidden /><ArrowRight className="size-4 rotate-90 md:rotate-0" aria-hidden />
            </div>
          )}
          <div className="glass-subtle rounded-xl p-3">
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-xs font-semibold text-slate-800">{z.label}</span>
              <span className="text-xs text-slate-500">{z.sub}</span>
            </div>
            <div className={cn("grid gap-2", z.ai && "sm:grid-cols-2")}>
              {z.ids.map((id) => {
                const Icon = STAGE_ICON[id];
                return (
                  <Link key={id} href={`/stages/${id}`} className="glass group flex items-center gap-2.5 rounded-xl px-3 py-2.5">
                    <span className="grid size-7 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600 transition-colors group-hover:bg-slate-200 group-hover:text-slate-900"><Icon className="size-4" /></span>
                    <span className="min-w-0 truncate text-sm font-medium text-slate-900">{STAGES.find((s) => s.id === id)!.title}</span>
                    <ArrowRight className="ml-auto size-4 shrink-0 text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 motion-reduce:transition-none" aria-hidden />
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
