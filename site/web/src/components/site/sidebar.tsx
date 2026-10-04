"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, Hash, House, Network, Menu, MessageSquareText, ScrollText, Table2, Workflow, X } from "lucide-react";
import { LOCAL, useContextStore } from "@/lib/context";
import { STAGES, STAGE_ICON } from "@/lib/stages";
import { cn } from "@/lib/utils";

const MAIN = [
  { href: "/", label: "Overview", icon: House },
  { href: "/playground", label: "Playground", icon: Workflow },
  { href: "/gnn", label: "GNN", icon: Network },
  { href: "/hashing", label: "Hashing", icon: Hash },
  { href: "/ask", label: "Ask", icon: MessageSquareText },
  // Local web container only: pages that show real names (built by another agent).
  ...(LOCAL ? [{ href: "/database", label: "Database", icon: Table2 }, { href: "/slow-log", label: "Slow log", icon: ScrollText }] : []),
];

/** HH:MM today, else the date. */
const when = (iso: string) => {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
};

/** Asked questions (local only): click selects the bundle every page renders from. */
function History() {
  const { list, current, refresh, select } = useContextStore();
  useEffect(() => { void refresh(); }, [refresh]);
  if (!list.length) return null;
  const remove = async (id: string) => {
    await fetch(`/api/history/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (current?.id === id) await select(null);
    await refresh();
  };
  return (
    <div>
      <div className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-slate-500">History</div>
      <ul className="space-y-0.5">
        {list.map((b) => (
          <li key={b.id} className={cn("group flex h-8 items-center gap-1.5 rounded-full pl-2.5 pr-1 text-xs text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-900", current?.id === b.id && "bg-slate-100 font-medium text-slate-900")}>
            <button type="button" onClick={() => select(b.id)} title={`${b.question} (${b.id})`} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
              {b.ok ? <Check className="size-3 shrink-0 text-slate-500" aria-label="answered" /> : <X className="size-3 shrink-0 text-signal" aria-label="failed" />}
              <span className="truncate">{b.question}</span>
              <span className="ml-auto shrink-0 font-mono text-xs text-slate-500">{when(b.created_at)}</span>
            </button>
            <button type="button" onClick={() => remove(b.id)} aria-label={`Delete ${b.question}`} className="grid size-5 shrink-0 place-items-center rounded-full text-slate-400 opacity-0 hover:bg-slate-200 hover:text-slate-900 focus:opacity-100 group-hover:opacity-100">
              <X className="size-3" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const item = (active: boolean) =>
    cn("group flex h-8 items-center gap-2 rounded-full px-2.5 text-sm text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-900", active && "bg-slate-100 font-medium text-slate-900");
  const nav = (
    <nav className="flex h-full flex-col gap-4 overflow-y-auto p-3" onClick={() => setOpen(false)}>
      <Link href="/" className="px-2.5 pt-1 text-lg font-semibold tracking-tight text-slate-900">Tiresias</Link>
      <ul className="space-y-0.5">
        {MAIN.map(({ href, label, icon: Icon }) => (
          <li key={href}><Link href={href} className={item(path === href)}><Icon className="size-4 text-slate-500 transition-colors group-hover:text-slate-900" />{label}</Link></li>
        ))}
      </ul>
      <div>
        <div className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-slate-500">Stages</div>
        <ul className="space-y-0.5">
          {STAGES.map((s) => {
            const Icon = STAGE_ICON[s.id];
            return (
              <li key={s.id}>
                <Link href={`/stages/${s.id}`} className={item(path === `/stages/${s.id}`)}>
                  <Icon className="size-4 text-slate-500 transition-colors group-hover:text-slate-900" />{s.title}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
      {LOCAL && <History />}
      <div className="mt-auto flex flex-wrap gap-x-3 gap-y-1 px-2 text-xs text-slate-600">
        <Link href="/privacy" className="hover:underline">Privacy</Link>
        <Link href="/terms" className="hover:underline">Terms</Link>
        <a href="https://github.com/Derpinator96/Tiresias" className="hover:underline">GitHub</a>
      </div>
    </nav>
  );
  return (
    <>
      <div className="glass-bar sticky top-0 z-40 flex h-12 items-center justify-between rounded-none px-3 lg:hidden">
        <Link href="/" className="text-sm font-semibold text-slate-900">Tiresias</Link>
        <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"} className="grid size-8 place-items-center rounded-full text-slate-700 hover:bg-slate-100">
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      <aside className={cn("glass-bar fixed bottom-3 left-3 top-3 z-50 w-56", open ? "block" : "hidden lg:block")}>{nav}</aside>
    </>
  );
}
