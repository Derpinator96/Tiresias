"use client";
import { useEffect, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Source, SqlBlock, Stat } from "@/components/playground/bits";
import type { AskJob } from "@/lib/ask-shared";
import { cn } from "@/lib/utils";

type State = AskJob & { poll_ms: number; events: string[] };

// Local web container only: rendered when the build sets NEXT_PUBLIC_BT_LOCAL=1. Shows real names
// (dehashed by the gateway on the private side); the toggle shows what the AI side saw.
export function LiveAsk() {
  const [question, setQuestion] = useState("");
  const [qid, setQid] = useState<string | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aiView, setAiView] = useState(false);
  const busy = !!qid && !state?.done && !error;

  useEffect(() => {
    if (!qid) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const r = await fetch(`/api/ask?qid=${encodeURIComponent(qid)}`, { cache: "no-store" });
      const body = await r.json();
      if (!live) return;
      if (!r.ok) return setError(body.error ?? `HTTP ${r.status}`);
      setState(body);
      if (!body.done) timer = setTimeout(tick, body.poll_ms);
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

  const a = state?.ask;
  return (
    <div className="glass-strong space-y-4 rounded-xl p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <span className="size-2 rounded-full bg-emerald-500" aria-hidden /> Live: this machine&apos;s gateway and AI service
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="For example: why is the monthly category report slow?" aria-label="Question" className="min-w-60 flex-1" />
        <button type="submit" disabled={!question.trim() || busy} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
        </button>
      </form>
      <Source>The question stays on the private network: the gateway matches it to query templates and sends the AI side only their codes.</Source>

      {error && <div className="rounded-lg border border-red-200 bg-red-50/80 p-3 text-sm text-red-800">{error}</div>}

      {state && !a && (
        <div className="inset-field p-3 text-sm text-slate-700">
          Working: {state.events.filter((e) => e.startsWith("tool ")).length} tool calls so far
          {state.events.filter((e) => e.startsWith("rate limited") || e.startsWith("LLM service unavailable")).map((e) => (
            <div key={e} className="mt-1 text-amber-800">{e}</div>
          ))}
        </div>
      )}

      {a && (
        <section>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-900">Answer</h3>
            <div className="flex rounded-md border border-slate-200 bg-white/70 p-0.5 text-xs">
              {[false, true].map((v) => (
                <button key={String(v)} onClick={() => setAiView(v)} className={cn("h-6 rounded px-2", aiView === v ? "bg-slate-900 text-white" : "text-slate-600")}>
                  {v ? "What the AI saw" : "Real names"}
                </button>
              ))}
            </div>
          </div>
          {a.status !== 200 ? (
            <div className="rounded-lg border border-red-200 bg-red-50/80 p-3 text-sm text-red-800">The LLM did not answer: {a.detail}</div>
          ) : a.checker !== "ok" ? (
            <div className="rounded-lg border border-red-200 bg-red-50/80 p-3 text-sm text-red-800">Answer blocked: it held numbers not found in any tool result ({a.unmatched?.join(", ")}).</div>
          ) : (
            <p className="inset-field whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{aiView ? a.hashed : a.real}</p>
          )}
        </section>
      )}

      {state?.done && state.error && <div className="rounded-lg border border-red-200 bg-red-50/80 p-3 text-sm text-red-800">Could not measure or write the SQL: {state.error}</div>}
      {a && !state?.done && <div className="inset-field flex items-center gap-2 p-3 text-sm text-slate-700"><Loader2 className="size-4 animate-spin" /> Measuring on the twin and writing the SQL</div>}

      {state?.done && !state.error && !state.results && <div className="inset-field p-3 text-sm text-slate-700">The search found no change worth its cost, so there is no SQL to apply.</div>}

      {state?.done && state.results && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-900">Time saved on the twin</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {state.results.map((t) => (
              <Stat key={t.template_id} label={aiView ? t.template_id : t.label} value={`${t.saved_ms.toFixed(1)} ms saved`} note={`${t.pct.toFixed(0)}% faster (${t.before_ms.toFixed(1)} to ${t.after_ms.toFixed(1)} ms)`} />
            ))}
          </div>
          <Source>
            Measured on a synthetic {state.rows ? `${state.rows.toLocaleString("en-US")}-row ` : ""}copy of the data, median of {state.sim?.runs} runs; not production.
          </Source>
          {aiView ? (
            <div className="inset-field p-3 text-sm text-slate-700">SQL hidden in the AI view: it holds real names.</div>
          ) : (
            <>
              <h3 className="text-sm font-semibold text-slate-900">SQL to apply</h3>
              <SqlBlock text={state.migration ?? ""} file="migration.sql" />
              <h3 className="text-sm font-semibold text-slate-900">Rollback</h3>
              <SqlBlock text={state.rollback ?? ""} file="rollback.sql" />
              <Source>The DBA runs these with psql. Nothing here touches production.</Source>
            </>
          )}
        </section>
      )}
    </div>
  );
}
