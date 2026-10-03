"use client";
// One line at the top of a page when a bundle is current: which question the figures belong to.
// Nothing when none (public build or nothing asked yet).
import { MessageSquareText } from "lucide-react";
import { useView } from "@/lib/view";
import { cn } from "@/lib/utils";

export function RunBanner({ className }: { className?: string }) {
  const v = useView();
  if (!v.live) return null;
  const sql = v.templateSqlReal ?? v.templateSql;
  return (
    <div className={cn("glass-subtle rounded-lg px-3 py-2 text-xs text-slate-700", className)}>
      <div className="flex items-center gap-2">
        <MessageSquareText className="size-3.5 shrink-0 text-blue-700" aria-hidden />
        <span className="min-w-0 truncate">
          Showing the run for: <span className="font-medium text-slate-900">{v.question}</span>
          {v.askedAt && <span className="text-slate-500"> (asked {new Date(v.askedAt).toLocaleString([], { hour12: false })})</span>}
        </span>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-slate-500">{v.id}</span>
      </div>
      {sql && <div className="mt-1 truncate font-mono text-[11px] text-slate-600" title={sql}>{sql}</div>}
    </div>
  );
}
