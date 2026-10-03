"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Source, SqlBlock, Stat } from "@/components/playground/bits";
import type { AskJob } from "@/lib/ask-shared";
import { useBundle, useContextStore } from "@/lib/context";
import { cn } from "@/lib/utils";

type State = AskJob & { poll_ms: number; events: string[]; bundle_ready: boolean };

const PAGES = [["Open in Playground", "/playground"], ["GNN", "/gnn"], ["Hashing", "/hashing"], ["Stage pages", "/stages/source"]];
const bad = "rounded-lg bg-signal-soft p-3 text-sm font-medium text-signal";

/** The answer, twin result and SQL of one job: the live one while it runs, or a saved bundle's. */
function Result({ job, live }: { job: AskJob; live: boolean }) {
  const [aiView, setAiView] = useState(false);
  const a = job.ask;
  return (
    <>
      {a && (
        <section>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">Answer</h3>
            <div className="glass-subtle flex rounded-md p-0.5 text-xs">
              {[false, true].map((v) => (
                <button key={String(v)} onClick={() => setAiView(v)} className={cn("h-6 rounded px-2", aiView === v ? "bg-ink text-white" : "text-slate-600")}>
                  {v ? "What the AI saw" : "Real names"}
                </button>
              ))}
            </div>
          </div>
          {a.status !== 200 ? (
            <div className={bad}>The LLM did not answer: {a.detail}</div>
          ) : a.checker !== "ok" ? (
            <div className={bad}>Answer blocked: numbers not in any tool result ({a.unmatched?.join(", ")}).</div>
          ) : (
            <p className="inset-field whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{aiView ? a.hashed : a.real}</p>
          )}
        </section>
      )}

      {job.done && job.error && <div className={bad}>Could not measure or write the SQL: {job.error}</div>}
      {live && a && !job.done && <div className="inset-field flex items-center gap-2 p-3 text-sm text-slate-700"><Loader2 className="size-4 animate-spin" /> Measuring on the twin and writing the SQL</div>}

      {job.done && !job.error && !job.results && <div className="inset-field p-3 text-sm text-slate-700">No change worth its cost, so no SQL to apply.</div>}

      {job.done && job.results && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-900">Time saved on the twin</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {job.results.map((t) => (
              <Stat key={t.template_id} label={aiView ? t.template_id : t.label} value={`${t.saved_ms.toFixed(1)} ms saved`} note={`${t.pct.toFixed(0)}% faster (${t.before_ms.toFixed(1)} to ${t.after_ms.toFixed(1)} ms)`} />
            ))}
          </div>
          <Source>synthetic {job.rows ? `${job.rows.toLocaleString("en-US")}-row ` : ""}twin, median of {job.sim?.runs} runs; not production</Source>
          {aiView ? (
            <div className="inset-field p-3 text-sm text-slate-700">SQL hidden in the AI view: it holds real names.</div>
          ) : (
            <>
              <h3 className="text-sm font-semibold text-slate-900">SQL to apply</h3>
              <SqlBlock text={job.migration ?? ""} file="migration.sql" />
              <h3 className="text-sm font-semibold text-slate-900">Rollback</h3>
              <SqlBlock text={job.rollback ?? ""} file="rollback.sql" />
              <Source>the DBA runs these with psql; nothing here touches production</Source>
            </>
          )}
        </section>
      )}
    </>
  );
}

/** Links to the pages that render from the current bundle. */
function PageLinks() {
  return (
    <div className="flex flex-wrap gap-2">
      {PAGES.map(([label, href]) => (
        <Link key={href} href={href} className="glass-subtle inline-flex h-7 items-center rounded-md px-2.5 text-xs font-medium text-ink hover:bg-white/70">{label}</Link>
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
    <div className="glass-strong space-y-4 rounded-xl p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <span className="size-2 rounded-full bg-accent" aria-hidden /> Live: local gateway and AI service
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="For example: why is the monthly category report slow?" aria-label="Question" className="min-w-60 flex-1" />
        <button type="submit" disabled={!question.trim() || busy} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
        </button>
      </form>
      <Source>the question stays private; the AI side gets template codes only</Source>

      {error && <div className={bad}>{error}</div>}

      {state && !state.ask && (
        <div className="inset-field p-3 text-sm text-slate-700">
          Working: {state.events.filter((e) => e.startsWith("tool ")).length} tool calls so far
          {state.events.filter((e) => e.startsWith("rate limited") || e.startsWith("LLM service unavailable")).map((e) => (
            <div key={e} className="mt-1 text-signal">{e}</div>
          ))}
        </div>
      )}

      {state && <Result key={state.question_id} job={state} live />}
      {state?.done && state.bundle_ready && <PageLinks />}

      {saved && (
        <>
          <div className="glass-subtle rounded-lg px-3 py-2 text-xs text-slate-600">
            From history: <span className="font-medium text-slate-900">{bundle.question}</span> <span className="font-mono text-xs text-slate-500">({bundle.id}, {new Date(bundle.created_at).toLocaleString("en-GB")})</span>
          </div>
          <Result key={bundle.id} job={bundle.job} live={false} />
          <PageLinks />
        </>
      )}
    </div>
  );
}
