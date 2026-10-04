"use client";
// One pill line at the top of a page when a bundle is current: which question the figures belong to.
// Nothing when none (public build or nothing asked yet).
import { MessageSquareText } from "lucide-react";
import { useView } from "@/lib/view";
import { cn } from "@/lib/utils";

export function RunBanner({ className }: { className?: string }) {
  const v = useView();
  if (!v.live) return null;
  const sql = v.templateSqlReal ?? v.templateSql;
  const asked = v.askedAt ? ` (asked ${new Date(v.askedAt).toLocaleString([], { hour12: false })})` : "";
  return (
    <div className={cn("pill flex h-8 max-w-full items-center gap-2 bg-white/80 px-3 text-xs text-slate-700 shadow-(--glass-shadow)", className)} title={`${v.question}${asked}\n${sql ?? ""}`}>
      <MessageSquareText className="size-3.5 shrink-0 text-slate-500" aria-hidden />
      <span className="min-w-0 truncate"><span className="font-medium text-slate-900">{v.question}</span></span>
      <span className="ml-auto shrink-0 font-mono text-slate-500">{v.id}</span>
    </div>
  );
}
