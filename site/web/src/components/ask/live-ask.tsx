"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Source, SqlBlock } from "@/components/playground/bits";
import type { AskJob } from "@/lib/ask-shared";
import { useBundle, useContextStore } from "@/lib/context";
import { Bento, Gauge } from "@/components/viz/charts";
import { cn } from "@/lib/utils";

type State = AskJob & { poll_ms: number; events: string[]; bundle_ready: boolean };

const PAGES = [["Open in Playground", "/playground"], ["GNN", "/gnn"], ["Hashing", "/hashing"], ["Stage pages", "/stages/source"]];
const seg = (on: boolean) => cn("h-7 pill px-2.5 text-sm", on ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70");

/** Error and blocked states: off-white, ink text, one signal dot (the dot is the only colour). */
function Bad({ children }: { children: React.ReactNode }) {
  return (
    <div className="inset-field flex items-start gap-2 p-3 text-sm text-ink">
      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-signal" aria-hidden /> <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </div>
  );
}

/** The answer, twin result and SQL of one job as Bento tiles: the live one while it runs, or a saved bundle's. */
function Result({ job, live }: { job: AskJob; live: boolean }) {
  const [aiView, setAiView] = useState(false);
  const a = job.ask;
  const best = job.results?.length ? Math.max(...job.results.map((t) => t.pct)) : null;
  return (
    <>
      {a && (
        <section className="glass min-w-0 p-5 md:col-span-7">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-slate-900">Answer</h3>
            <div className="glass-subtle flex pill p-0.5">
              {[false, true].map((v) => (
                <button key={String(v)} onClick={() => setAiView(v)} className={seg(aiView === v)}>{v ? "What the AI saw" : "Real names"}</button>
              ))}
            </div>
          </div>
          {a.status !== 200 ? (
            <Bad>The LLM did not answer: {a.detail}</Bad>
          ) : a.checker !== "ok" ? (
            <Bad>Answer blocked: numbers not in any tool result ({a.unmatched?.join(", ")}).</Bad>
          ) : (
            <p className="inset-field max-h-96 overflow-auto whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{aiView ? a.hashed : a.real}</p>
          )}
        </section>
      )}

      <div className={cn("flex min-w-0 flex-col gap-3", a ? "md:col-span-5" : "md:col-span-12")}>
        {job.done && job.error && <Bad>Could not measure or write the SQL: {job.error}</Bad>}
        {live && a && !job.done && <div className="inset-field flex items-center gap-2 p-3 text-sm text-slate-700"><Loader2 className="size-4 animate-spin" /> Measuring on the twin and writing the SQL</div>}
        {job.done && !job.error && !job.results && <div className="glass p-5 text-sm text-slate-700">No change worth its cost, so no SQL to apply.</div>}
        {job.done && job.results && (
          <>
            <section className="tile-lime space-y-2 p-5">
              <h3 className="text-sm font-semibold">Time saved on the twin</h3>
              {job.results.map((t) => (
                <div key={t.template_id} className="min-w-0">
                  <div className="truncate text-xs text-slate-700" title={aiView ? t.template_id : t.label}>{aiView ? t.template_id : t.label}</div>
                  <div className="font-mono text-3xl font-semibold tracking-tight">{t.saved_ms.toFixed(1)}<span className="text-lg"> ms</span></div>
                  <div className="font-mono text-xs text-slate-700">{t.before_ms.toFixed(1)} to {t.after_ms.toFixed(1)} ms</div>
                </div>
              ))}
              <Source>synthetic {job.rows ? `${job.rows.toLocaleString("en-US")}-row ` : ""}twin, median of {job.sim?.runs} runs; not production</Source>
            </section>
            {best !== null && <div className="glass p-5"><Gauge value={best} unit="%" label="best speedup on the twin" /></div>}
          </>
        )}
      </div>

      {job.done && job.results && (aiView ? (
        <div className="inset-field p-3 text-sm text-slate-700 md:col-span-12">SQL hidden in the AI view: it holds real names.</div>
      ) : (
        <>
          {([["SQL to apply", job.migration, "migration.sql"], ["Rollback", job.rollback, "rollback.sql"]] as const).map(([title, text, file]) => (
            <section key={file} className="glass min-w-0 p-5 md:col-span-6">
              <h3 className="mb-2 text-base font-semibold text-slate-900">{title}</h3>
              <div className="max-h-72 overflow-auto rounded-xl"><SqlBlock text={text ?? ""} file={file} /></div>
              <Source>the DBA runs this with psql; nothing here touches production</Source>
            </section>
          ))}
        </>
      ))}
    </>
  );
}

/** Links to the pages that render from the current bundle. */
function PageLinks() {
  return (
    <div className="flex flex-wrap gap-2">
      {PAGES.map(([label, href]) => (
        <Link key={href} href={href} className="glass-subtle inline-flex h-7 items-center pill px-3 text-sm font-medium text-slate-600 hover:text-ink">{label}</Link>
      ))}
    </div>
  );
}

// Local web container only: rendered when the build sets NEXT_PUBLIC_BT_LOCAL=1. Shows real names
// (dehashed by the gateway on the private side); the toggle shows what the AI side saw. With no
// live job, shows the history-selected bundle (sidebar) so an old question reads as it did.
export function LiveAsk() {
  const [question, setQuestion] = useState("");
  const [qid, setQid] = useState<string | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bundle = useBundle();
  const busy = !!qid && !state?.done && !error;

  useEffect(() => {
    if (!qid) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const r = await fetch(`/api/ask?qid=${encodeURIComponent(qid)}`, { cache: "no-store" });
      const body: State & { error?: string } = await r.json();
      if (!live) return;
      if (!r.ok) return setError(body.error ?? `HTTP ${r.status}`);
      setState(body);
      if (!body.done || !body.bundle_ready) timer = setTimeout(tick, body.poll_ms);
      else { // the saved bundle becomes the current context for every page
        const s = useContextStore.getState();
        await s.refresh();
        await s.select(body.question_id);
      }
    };
    tick();
    return () => { live = false; clearTimeout(timer); };
  }, [qid]);

  const ask = async () => {
    setError(null);
    setState(null);
    setQid(null);
    const r = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) });
    const body = await r.json();
    if (!r.ok) return setError(body.error ?? `HTTP ${r.status}`);
    setQid(body.question_id);
  };

  const saved = !state && !error && bundle;
  return (
    <Bento>
      <div className="glass space-y-2 p-4 md:col-span-12">
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="For example: why is the monthly category report slow?" aria-label="Question" className="min-w-0 flex-1 basis-60" />
          <button type="submit" disabled={!question.trim() || busy} className="inline-flex h-8 items-center gap-1.5 pill bg-ink px-3.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
          </button>
        </form>
        <div className="flex flex-wrap items-center gap-2">
          {saved && (
            <div className="glass-subtle inline-flex min-w-0 max-w-full items-center gap-2 pill px-3 py-1 text-xs text-slate-600">
              <span className="shrink-0">From history</span>
              <span className="truncate font-medium text-slate-900">{bundle.question}</span>
              <span className="hidden shrink-0 font-mono text-slate-500 sm:inline">{bundle.id}, {new Date(bundle.created_at).toLocaleString("en-GB")}</span>
            </div>
          )}
          {(saved || (state?.done && state.bundle_ready)) && <PageLinks />}
        </div>
        <Source>live, local gateway and AI service; the question stays private, the AI side gets template codes only</Source>
      </div>

      {error && <div className="md:col-span-12"><Bad>{error}</Bad></div>}

      {state && !state.ask && (
        <div className="inset-field p-3 text-sm text-slate-700 md:col-span-12">
          Working: {state.events.filter((e) => e.startsWith("tool ")).length} tool calls so far
          {state.events.filter((e) => e.startsWith("rate limited") || e.startsWith("LLM service unavailable")).map((e) => (
            <div key={e} className="mt-1 flex items-center gap-2 text-ink"><span className="size-2 shrink-0 rounded-full bg-signal" aria-hidden />{e}</div>
          ))}
        </div>
      )}

      {state && <Result key={state.question_id} job={state} live />}
      {saved && <Result key={bundle.id} job={bundle.job} live={false} />}
    </Bento>
  );
}
