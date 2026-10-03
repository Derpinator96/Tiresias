import Link from "next/link";
import { ArrowRight, ClipboardCheck, Cpu, Database, FlaskConical, Grid3x3, Lock, MessageSquareCode, Pickaxe, ShieldCheck } from "lucide-react";
import { STAGES, type StageId } from "@/lib/stages";
import { cn } from "@/lib/utils";

const ICON: Record<StageId, typeof Database> = {
  source: Database, gateway: ShieldCheck, miner: Pickaxe, gnn: Cpu, rl: Grid3x3, llm: MessageSquareCode, twin: FlaskConical, dba: ClipboardCheck,
};
const ZONES: { label: string; sub: string; ids: StageId[]; ai?: boolean }[] = [
  { label: "Private network", sub: "real names and data", ids: ["source", "gateway"] },
  { label: "AI zone", sub: "hashed codes only", ids: ["miner", "gnn", "rl", "llm"], ai: true },
  { label: "Private network", sub: "measured, then approved", ids: ["twin", "dba"] },
];

/** The 8 stages across the trust boundary; every node links to its page. */
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
          <div className={cn("rounded-xl border border-dashed p-3", z.ai ? "border-blue-300 bg-blue-50/40" : "border-slate-300 bg-white/30")}>
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-xs font-semibold text-slate-800">{z.label}</span>
              <span className="text-[11px] text-slate-500">{z.sub}</span>
            </div>
            <div className={cn("grid gap-2", z.ai && "sm:grid-cols-2")}>
              {z.ids.map((id) => {
                const i = STAGES.findIndex((s) => s.id === id);
                const Icon = ICON[id];
                return (
                  <Link key={id} href={`/stages/${id}`} className="glass group flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-white/90">
                    <span className="grid size-7 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-700 transition-colors group-hover:border-slate-300 group-hover:text-slate-900"><Icon className="size-4" /></span>
                    <span className="min-w-0">
                      <span className="block font-mono text-[10px] text-slate-500">{i + 1}</span>
                      <span className="block truncate text-sm font-medium text-slate-900">{STAGES[i].title}</span>
                    </span>
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
