"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BellRing, Check, SquareTerminal, Hash, House, Network, Menu, MessageSquareText, ScrollText, Table2, Workflow, X } from "lucide-react";
import { LOCAL, useContextStore } from "@/lib/context";
import { STAGES, STAGE_ICON, STAGE_TINT } from "@/lib/stages";
import { cn } from "@/lib/utils";

// Tab tints (plan section 5): bg = active tile, soft = the faint icon tile when not active.
const T = {
  lime: { bg: "bg-lime", soft: "bg-lime/40" }, sky: { bg: "bg-sky", soft: "bg-sky/40" }, peach: { bg: "bg-peach", soft: "bg-peach/40" },
  sand: { bg: "bg-sand", soft: "bg-sand/40" }, leaf: { bg: "bg-leaf", soft: "bg-leaf/40" }, rose: { bg: "bg-rose", soft: "bg-rose/40" },
};
type Tint = { bg: string; soft: string };
const MAIN: { href: string; label: string; icon: typeof House; tint: Tint }[] = [
  { href: "/", label: "Overview", icon: House, tint: T.lime },
  { href: "/playground", label: "Playground", icon: Workflow, tint: T.lime },
  { href: "/gnn", label: "GNN", icon: Network, tint: T.sky },
  { href: "/hashing", label: "Hashing", icon: Hash, tint: T.peach },
  { href: "/ask", label: "Ask", icon: MessageSquareText, tint: T.rose },
  // Local web container only: pages that show real names (built by another agent).
  ...(LOCAL ? [{ href: "/database", label: "Database", icon: Table2, tint: T.leaf }, { href: "/slow-log", label: "Slow log", icon: ScrollText, tint: T.sand },
    { href: "/alerts", label: "Alerts", icon: BellRing, tint: T.rose },
    { href: "/analytics", label: "Analytics", icon: Activity, tint: T.sky },
    { href: "/workbench", label: "Workbench", icon: SquareTerminal, tint: T.peach }] : []),
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

// Desktop: a 64px icon rail that widens to 224px on hover or keyboard focus, over the page
// (fixed, so no layout shift). Labels fade in with it. Phone: top bar plus a menu sheet.
const fade = "whitespace-nowrap transition-opacity duration-200 lg:opacity-0 lg:group-hover/side:opacity-100 lg:group-focus-within/side:opacity-100 motion-reduce:transition-none";
const hideCollapsed = "lg:invisible lg:group-hover/side:visible lg:group-focus-within/side:visible";

export function Sidebar() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const item = (active: boolean, tint: Tint) =>
    cn("flex h-10 items-center gap-3 rounded-2xl text-sm text-slate-700 transition-colors hover:text-slate-900", active ? cn(tint.bg, "font-medium text-ink") : "hover:bg-mint");
  const tile = "grid size-10 shrink-0 place-items-center";
  const link = (href: string, label: string, Icon: typeof House, tint: Tint) => (
    <li key={href}>
      <Link href={href} className={item(path === href, tint)} aria-label={label}>
        <span className={cn(tile, "rounded-2xl", path !== href && tint.soft)}><Icon className="size-4" /></span><span className={fade}>{label}</span>
      </Link>
    </li>
  );
  const nav = (
    <nav className="flex h-full flex-col gap-3 overflow-y-auto overflow-x-hidden p-3 [scrollbar-width:none]" onClick={() => setOpen(false)}>
      <Link href="/" className="flex items-center gap-3" aria-label="Tiresias overview">
        <span className={cn(tile, "rounded-2xl bg-lime text-base font-semibold text-ink")}>T</span>
        <span className={cn(fade, "text-lg font-semibold tracking-tight text-slate-900")}>Tiresias</span>
      </Link>
      <ul className="space-y-1">{MAIN.map(({ href, label, icon, tint }) => link(href, label, icon, tint))}</ul>
      <div>
        <div className={cn(fade, "h-4 px-3 text-xs font-medium uppercase tracking-wide text-slate-500")}>Stages</div>
        <ul className="space-y-1">{STAGES.map((s) => link(`/stages/${s.id}`, s.title, STAGE_ICON[s.id], STAGE_TINT[s.id]))}</ul>
      </div>
      {LOCAL && <div className={cn(fade, hideCollapsed)}><History /></div>}
      <div className={cn(fade, hideCollapsed, "mt-auto flex gap-x-3 px-2 text-xs text-slate-600")}>
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
      <aside className={cn("glass-bar group/side fixed bottom-3 left-3 top-3 z-50 w-56 rounded-3xl transition-[width] duration-200 lg:block lg:w-16 lg:hover:w-56 lg:hover:shadow-(--glass-shadow-lg) lg:focus-within:w-56 motion-reduce:transition-none", open ? "block" : "hidden")}>{nav}</aside>
    </>
  );
}
