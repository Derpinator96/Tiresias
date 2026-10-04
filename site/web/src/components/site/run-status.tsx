"use client";
// The run pill at the top of every page: an Ask input when idle, the live stage while a question
// runs (from the one poller in src/lib/context.ts), "Fresh result" for a few seconds when it
// lands, then which question the pages are showing. Public build: renders nothing.
import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, CircleAlert, Loader2, Send } from "lucide-react";
import { LOCAL, useBundle, useContextStore } from "@/lib/context";
import { ORDER } from "@/lib/progress";
import { STAGES, STAGE_ICON } from "@/lib/stages";
import { cn } from "@/lib/utils";

const TITLE = Object.fromEntries(STAGES.map((s) => [s.id, s.title])) as Record<(typeof STAGES)[number]["id"], string>;

/** "just now", "4 min ago", "3 h ago", else the date. */
function ago(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB");
}

function AskInput() {
  const start = useContextStore((s) => s.start);
  const [q, setQ] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!q.trim() || busy) return;
    setBusy(true);
    const e = await start(q.trim());
    setBusy(false);
    setErr(e);
    if (!e) setQ("");
  };
  return (
    <form className="flex min-w-0 flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask why a query is slow" aria-label="Ask why a query is slow"
        className="h-8 min-w-0 flex-1 pill bg-slate-100/80 px-3.5 text-sm text-ink outline-none placeholder:text-slate-500 focus-visible:ring-2 focus-visible:ring-ink/20" />
      <button type="submit" disabled={!q.trim() || busy} aria-label="Send question" className="inline-flex size-8 shrink-0 items-center justify-center pill bg-ink text-white hover:bg-slate-800 disabled:opacity-40">
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
      </button>
      {err && <span className="flex shrink-0 items-center gap-1 text-xs text-ink"><CircleAlert className="size-3.5 text-signal" />{err}</span>}
    </form>
  );
}

export function RunStatus() {
  const running = useContextStore((s) => s.running);
  const fresh = useContextStore((s) => s.fresh);
  const bundle = useBundle();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  if (!LOCAL) return null;

  let body: React.ReactNode;
  if (running && !running.error) {
    // progress = the furthest stage reached, so the count never runs backwards when the agent
    // revisits an earlier tool; the chip still names the stage working right now
    const i = Math.max(...running.reached.map((s) => ORDER.indexOf(s))), Icon = STAGE_ICON[running.stage];
    const last = running.events.at(-1);
    body = (
      <>
        <div className="flex min-w-0 flex-1 items-center gap-3 text-sm">
          <Loader2 className="size-4 shrink-0 animate-spin text-ink" />
          <span className="min-w-0 max-w-[40%] truncate font-medium text-ink" title={running.question}>{running.question}</span>
          <span className="inline-flex shrink-0 items-center gap-1.5 pill bg-rose px-2.5 py-0.5 text-xs font-medium text-ink"><Icon className="size-3.5" />{TITLE[running.stage]}</span>
          <span className="shrink-0 text-xs text-slate-600">step {i + 1} of {ORDER.length}</span>
          {running.replay ? (
            <span className="shrink-0 pill bg-lime px-2.5 py-0.5 text-xs font-medium text-ink" title="replay speed, not the real duration">
              Replay of {running.replay.id}, recorded {new Date(running.replay.created_at).toLocaleString("en-GB")}{running.replay.seconds != null && `; real LLM time ${running.replay.seconds.toFixed(1)} s`}
            </span>
          ) : <span className="shrink-0 font-mono text-xs text-slate-600">{Math.max(0, Math.floor((now - running.startedAt) / 1000))} s</span>}
          {last && <span className="min-w-0 truncate font-mono text-xs text-slate-500" title={last}>{last.replace(/ ->.*$/, "")}</span>}
        </div>
        <div className="absolute inset-x-4 bottom-0 h-0.5 overflow-hidden rounded-full bg-slate-200/70" aria-hidden>
          <div className="run-shimmer h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: `${((i + 1) / ORDER.length) * 100}%` }} />
        </div>
      </>
    );
  } else if (fresh && bundle?.id === fresh) {
    body = (
      <div className="flex min-w-0 flex-1 items-center gap-3 text-sm">
        <span className="inline-flex shrink-0 items-center gap-1.5 pill bg-lime px-2.5 py-0.5 text-xs font-semibold text-ink"><Check className="size-3.5" />Fresh result</span>
        <span className="min-w-0 truncate font-medium text-ink">{bundle.question}</span>
        <Link href="/ask" className="shrink-0 text-xs font-medium text-ink underline underline-offset-2">open</Link>
      </div>
    );
  } else {
    body = (
      <>
        {running?.error && (
          <span className="flex min-w-0 max-w-[45%] items-center gap-1.5 text-xs text-ink" title={running.error}>
            <CircleAlert className="size-3.5 shrink-0 text-signal" /><span className="truncate">Run failed: {running.error}</span>
          </span>
        )}
        {!running?.error && bundle && (
          <span className="min-w-0 max-w-[45%] truncate text-xs text-slate-600" title={bundle.question}>
            Showing: <span className="font-medium text-ink">{bundle.question}</span>, asked {ago(bundle.created_at, now)}
          </span>
        )}
        <AskInput />
      </>
    );
  }

  return (
    <div className="sticky top-0 z-30 px-4 pt-3 md:px-6">
      <div className={cn("glass-bar relative flex min-h-12 items-center gap-3 pill px-4 py-2", fresh && bundle?.id === fresh && "fresh-flash")} role="status" aria-live="polite">
        {body}
      </div>
      {/* moving highlight on the progress bar; none under reduced motion */}
      <style>{`.run-shimmer{background-image:linear-gradient(90deg,transparent 0,rgb(240 255 151/.9) 50%,transparent 100%);background-size:40% 100%;background-repeat:no-repeat;animation:run-shimmer 1.4s linear infinite}@keyframes run-shimmer{from{background-position:-40% 0}to{background-position:140% 0}}@media (prefers-reduced-motion:reduce){.run-shimmer{animation:none}}`}</style>
    </div>
  );
}
