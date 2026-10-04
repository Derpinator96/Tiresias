import Link from "next/link";
import { Lock } from "lucide-react";
import { STAGES, STAGE_ICON, type StageId } from "@/lib/stages";
import { cn } from "@/lib/utils";

const ZONES: { label: string; ids: StageId[]; ai?: boolean }[] = [
  { label: "Private: real names", ids: ["source", "gateway"] },
  { label: "AI zone: hashed codes only", ids: ["miner", "gnn", "rl", "llm"], ai: true },
  { label: "Private: measured, approved", ids: ["twin", "dba"] },
];

/** The 8 stages as a compact chain of round icon tiles in 3 trust zones; each links to its page,
 *  the stage name shows on hover (title) and to screen readers (aria-label). */
export function PipelineMap() {
  return (
    <div className="flex flex-wrap items-start gap-2">
      {ZONES.map((z, zi) => (
        <div key={zi} className="flex items-start gap-2">
          {zi > 0 && <Lock className="mt-3.5 size-3.5 shrink-0 text-slate-400" aria-label="trust boundary" />}
          <div>
            <div className={cn("flex gap-1.5 rounded-full p-1.5", z.ai ? "bg-ink" : "bg-mint")}>
              {z.ids.map((id) => {
                const Icon = STAGE_ICON[id];
                const title = STAGES.find((s) => s.id === id)!.title;
                return (
                  <Link key={id} href={`/stages/${id}`} title={title} aria-label={title}
                    className={cn("grid size-8 place-items-center rounded-full transition-transform hover:-translate-y-0.5 motion-reduce:transition-none", z.ai ? "bg-white/10 text-white hover:bg-lime hover:text-ink" : "bg-white text-slate-700 hover:bg-lime hover:text-ink")}>
                    <Icon className="size-4" />
                  </Link>
                );
              })}
            </div>
            <div className="mt-1 px-1 text-xs text-slate-500">{z.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
