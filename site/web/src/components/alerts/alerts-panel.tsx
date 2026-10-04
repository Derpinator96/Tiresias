"use client";
// Slow-query alerts for the signed-in DBA: the demo trigger, the list of sent alerts and the full
// stats of one alert (?id=, the link in the email). Local web app only.
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BellRing, Inbox, Loader2, LogOut, MailCheck, MailWarning } from "lucide-react";
import { Source, SqlBlock } from "@/components/playground/bits";
import { Bad } from "@/components/ask/data-ask";
import { Bento } from "@/components/viz/charts";
import { LOCAL } from "@/lib/context";
import { alertLines, type Alert } from "@/lib/alerts-shared";
import { cn } from "@/lib/utils";

type Me = { email: string; name: string; role: "dba" | "analyst"; inbox_url: string };
const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });
const noComments = (sql: string) => sql.replace(/\/\*[\s\S]*?\*\/|--[^\n]*/g, "").trim();

function Stats({ a }: { a: Alert }) {
  const stat = (label: string, value: string) => (
    <div><div className="text-xs text-slate-600">{label}</div><div className="font-mono text-2xl font-semibold tracking-tight text-ink">{value}</div></div>
  );
  return (
    <>
      <section className="glass min-w-0 space-y-3 p-5 md:col-span-12">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-900">Alert {a.id}</h3>
          <span className="text-xs text-slate-600">{new Date(a.created_at).toLocaleString("en-GB")}, to {a.to}</span>
        </div>
        <SqlBlock text={noComments(a.sql)} />
        <div className="flex flex-wrap gap-8">
          {stat("average", `${n(a.mean_ms)} ms`)}
          {stat("calls", a.calls.toLocaleString("en-US"))}
          {stat("total time", `${n(a.total_ms / 1000)} s`)}
          {stat("slow threshold", `${n(a.threshold_ms)} ms`)}
          {a.twin && stat("on the twin after the fix", `${n(a.twin.after_ms)} ms`)}
        </div>
        <ul className="space-y-1 text-sm text-slate-800">{alertLines(a).map((l, i) => <li key={i}>{l}</li>)}</ul>
        <div className="flex items-center gap-2 text-sm">
          {a.emailed ? <><MailCheck className="size-4 text-ink" /> Email sent to {a.to}</> : <><MailWarning className="size-4 text-signal" /> Email not sent: {a.email_error}</>}
        </div>
        <Source>pg-prod slow log (pg_stat_statements) for {a.template_id}; fix from the recorded search and /v1/approve; twin numbers in {a.twin_mode} mode</Source>
      </section>
      <section className="glass min-w-0 p-5 md:col-span-6"><h3 className="mb-2 text-base font-semibold text-slate-900">SQL to apply</h3><SqlBlock text={a.migration || "-- no change found"} file="migration.sql" /></section>
      <section className="glass min-w-0 p-5 md:col-span-6"><h3 className="mb-2 text-base font-semibold text-slate-900">Rollback</h3><SqlBlock text={a.rollback || "-- nothing to roll back"} file="rollback.sql" /></section>
    </>
  );
}

export function AlertsPanel() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [list, setList] = useState<Alert[]>([]);
  const [shown, setShown] = useState<Alert | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch("/api/auth/me", { cache: "no-store" });
    if (!r.ok) return setMe(null);
    const m: Me = await r.json();
    setMe(m);
    if (m.role !== "dba") return;
    const l: Alert[] = await (await fetch("/api/alerts", { cache: "no-store" })).json();
    setList(l);
    const id = new URLSearchParams(window.location.search).get("id");
    if (id) {
      const one = await fetch(`/api/alerts/item?id=${encodeURIComponent(id)}`, { cache: "no-store" });
      if (one.ok) setShown(await one.json());
      else setErr("That alert does not exist or belongs to another account.");
    } else setShown(l[0] ?? null);
  }, []);
  useEffect(() => {
    if (!LOCAL) return;
    const t = setTimeout(() => void load(), 0);
    return () => clearTimeout(t);
  }, [load]);

  if (!LOCAL) return <p className="text-sm text-slate-700">Alerts exist only in the local web app.</p>;
  if (me === undefined) return <p className="mt-6 flex items-center gap-2 text-sm text-slate-600"><Loader2 className="size-4 animate-spin" /> Loading</p>;
  if (me === null) {
    const next = encodeURIComponent(`/alerts${typeof window === "undefined" ? "" : window.location.search}`);
    return (
      <div className="glass mt-6 max-w-md space-y-3 p-6">
        <p className="text-sm text-slate-800">Sign in to see slow-query alerts and get them by email.</p>
        <div className="flex gap-2">
          <Link href={`/signin?next=${next}`} className="inline-flex h-9 items-center pill bg-ink px-4 text-sm font-medium text-white">Sign in</Link>
          <Link href={`/signup?next=${next}`} className="glass-subtle inline-flex h-9 items-center pill px-4 text-sm font-medium text-ink">Create account</Link>
        </div>
      </div>
    );
  }

  if (me.role !== "dba") {
    return <div className="glass mt-6 max-w-lg p-6 text-sm text-slate-800">Signed in as {me.email} with the analyst role. Alerts are for DBAs; use the <Link href="/workbench" className="font-medium text-ink underline">Workbench</Link> to run queries.</div>;
  }

  const trigger = async () => {
    setBusy(true);
    setErr(null);
    const r = await fetch("/api/alerts", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    const body = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    setBusy(false);
    if (!r.ok) return setErr(body.error);
    setShown(body);
    setList((l) => [body, ...l]);
    window.history.replaceState(null, "", `/alerts?id=${body.id}`);
  };
  const signout = async () => {
    await fetch("/api/auth/signout", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    router.replace("/signin");
  };

  return (
    <Bento className="mt-6">
      <section className="tile-ink space-y-3 p-5 md:col-span-8">
        <h3 className="text-base font-semibold text-lime">Slow-query alert</h3>
        <p className="text-sm text-white/80">Picks one of the slow queries already in pg-prod&apos;s slow log, works out the fix and emails it to {me.email}.</p>
        <button type="button" onClick={() => void trigger()} disabled={busy}
          className="inline-flex h-10 items-center gap-2 pill bg-lime px-5 text-sm font-semibold text-ink hover:bg-lime/90 disabled:opacity-50">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <BellRing className="size-4" />} Generate slow-log alert
        </button>
        <div className="text-xs text-white/60">demo trigger: replays a query already in the slow log; nothing is reseeded</div>
      </section>
      <section className="glass space-y-2 p-5 md:col-span-4">
        <div className="text-sm text-slate-700">Signed in as <span className="font-medium text-ink">{me.name}</span><br />{me.email}</div>
        <a href={me.inbox_url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 pill bg-ink px-3 text-sm font-medium text-white"><Inbox className="size-4" /> Open the mail inbox</a>
        <button type="button" onClick={() => void signout()} className="ml-2 inline-flex h-8 items-center gap-1.5 pill px-3 text-sm text-slate-600 hover:text-ink"><LogOut className="size-4" /> Sign out</button>
      </section>
      {err && <div className="md:col-span-12"><Bad>{err}</Bad></div>}
      {shown && <Stats key={shown.id} a={shown} />}
      {list.length > 0 && (
        <section className="glass min-w-0 p-5 md:col-span-12">
          <h3 className="mb-2 text-base font-semibold text-slate-900">Sent alerts</h3>
          <ul className="space-y-1">
            {list.map((a) => (
              <li key={a.id}>
                <button type="button" onClick={() => { setShown(a); window.history.replaceState(null, "", `/alerts?id=${a.id}`); }}
                  className={cn("w-full truncate rounded-xl px-3 py-2 text-left text-sm hover:bg-slate-100", shown?.id === a.id && "bg-slate-100")}>
                  <span className="font-mono text-xs text-slate-500">{new Date(a.created_at).toLocaleTimeString("en-GB")}</span>{" "}
                  {n(a.mean_ms)} ms, {noComments(a.sql).slice(0, 90)}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Bento>
  );
}
