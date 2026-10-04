"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Loader2, Play, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Source, SqlBlock } from "@/components/playground/bits";
import type { AskJob } from "@/lib/ask-shared";
import { useBundle, useContextStore, type Running } from "@/lib/context";
import { Bento, Gauge, useCountUp, useGrown } from "@/components/viz/charts";
import { glitchFrame } from "@/lib/glitch";
import { flagNumbers } from "@/lib/flag";
import { twinNote } from "@/lib/run-view";
import { plainSummary } from "@/lib/summary";
import { Bad, DataAsk } from "@/components/ask/data-ask";
import { ORDER } from "@/lib/progress";
import { STAGES, STAGE_ICON } from "@/lib/stages";
import { cn } from "@/lib/utils";

const PAGES = [["Open in Playground", "/playground"], ["GNN", "/gnn"], ["Hashing", "/hashing"], ["Stage pages", "/stages/source"]];
const seg = (on: boolean) => cn("h-7 pill px-2.5 text-sm", on ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70");

/** A blocked answer's draft with each rejected number marked. */
function Draft({ text, unmatched }: { text: string; unmatched: string[] }) {
  return (
    <p className="inset-field max-h-96 overflow-auto whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">
      {flagNumbers(text, unmatched).map((p, i) => p.flagged
        ? <mark key={i} className="rounded bg-signal-soft px-0.5 font-semibold text-signal">{p.text}</mark>
        : <span key={i}>{p.text}</span>)}
    </p>
  );
}

const GLITCH_MS = 900; // same settle time as the hashing page

/** The text, but a change scrambles into the new text left to right (the hashing glitch). */
function useGlitch(text: string): string {
  const [shown, setShown] = useState(text);
  const prev = useRef(text);
  useEffect(() => {
    const from = prev.current;
    prev.current = text;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const t0 = performance.now();
    let id = 0;
    const step = () => {
      const t = from === text || reduce ? 1 : Math.min(1, (performance.now() - t0) / GLITCH_MS);
      setShown(glitchFrame(from, text, t, Math.random));
      if (t < 1) id = window.setTimeout(step, 30);
    };
    id = window.setTimeout(step, 0);
    return () => clearTimeout(id);
  }, [text]);
  return shown;
}

function AnswerText({ text }: { text: string }) {
  return <p className="inset-field max-h-96 overflow-auto whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{useGlitch(text)}</p>;
}

type Saved = NonNullable<AskJob["results"]>[number];

/** One template's time saved, counting up, with its before bar shrinking to the after bar. */
function SavedTime({ t, label }: { t: Saved; label: string }) {
  const saved = useCountUp(t.saved_ms, 1200), before = useCountUp(t.before_ms, 1200), after = useCountUp(t.after_ms, 1200);
  const grown = useGrown();
  const ratio = t.before_ms > 0 ? t.after_ms / t.before_ms : 1;
  return (
    <div className="min-w-0">
      <div className="truncate text-xs text-slate-700" title={label}>{label}</div>
      <div className="font-mono text-3xl font-semibold tracking-tight">{saved.toFixed(1)}<span className="text-lg"> ms</span></div>
      <div className="font-mono text-xs text-slate-700">{before.toFixed(1)} to {after.toFixed(1)} ms</div>
      <div className="mt-1.5 h-2 rounded-full bg-white/60" aria-hidden>
        <div className="h-full origin-left rounded-full bg-ink transition-transform delay-300 duration-1000 ease-out motion-reduce:transition-none" style={{ transform: `scaleX(${grown ? ratio : 1})` }} />
      </div>
    </div>
  );
}

/** The outcome in plain words, built from the job's data, not the LLM (src/lib/summary.ts). */
function Plain({ job, question }: { job: AskJob; question: string }) {
  const { verdict, asked, outcome } = plainSummary(job, question);
  if (!verdict && !asked.length && !outcome.length) return null;
  const list = (title: string, items: string[]) => items.length > 0 && (
    <div>
      <div className="mb-1 text-xs text-white/60">{title}</div>
      <ul className="space-y-1 text-sm text-white">{items.map((t, i) => <li key={i} className="[overflow-wrap:anywhere]">{t}</li>)}</ul>
    </div>
  );
  return (
    <section className="tile-ink min-w-0 space-y-3 p-5 md:col-span-12">
      <h3 className="text-base font-semibold text-lime">In plain words</h3>
      {verdict && <p className="text-lg font-semibold text-white">{verdict}</p>}
      {list("What you asked about", asked)}
      {list("What to do", outcome)}
      <div className="text-xs text-white/50">written from the measured results and the SQL, not by the LLM; real names, local only</div>
    </section>
  );
}

/** The answer, twin result and SQL of one job as Bento tiles: the live one while it runs, or a saved bundle's. */
function Result({ job, question, live, flash = false, llmTime }: { job: AskJob; question: string; live: boolean; flash?: boolean; llmTime?: string | null }) {
  const [aiView, setAiView] = useState(false);
  const a = job.ask;
  const best = job.results?.length ? Math.max(...job.results.map((t) => t.pct)) : null;
  return (
    <>
      {!aiView && <Plain job={job} question={question} />}
      {a && (
        <section className={cn("glass min-w-0 p-5 md:col-span-7", flash && "fresh-flash")}>
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
            <div className="space-y-2">
              <Bad>Answer blocked by the number checker: {a.unmatched?.join(", ")} {a.unmatched?.length === 1 ? "is" : "are"} in no tool result.</Bad>
              {(aiView ? a.hashed : a.real) && (
                <>
                  <p className="text-xs text-slate-600">The LLM&apos;s draft, not verified. Highlighted numbers are in no tool result; everything else on this page comes from the tools.</p>
                  <Draft text={(aiView ? a.hashed : a.real) ?? ""} unmatched={a.unmatched ?? []} />
                </>
              )}
            </div>
          ) : (
            <AnswerText text={(aiView ? a.hashed : a.real) ?? ""} />
          )}
        </section>
      )}

      <div className={cn("flex min-w-0 flex-col gap-3", a ? "md:col-span-5" : "md:col-span-12")}>
        {job.done && job.error && <Bad>Could not measure or write the SQL: {job.error}</Bad>}
        {live && a && !job.done && <div className="inset-field flex items-center gap-2 p-3 text-sm text-slate-700"><Loader2 className="size-4 animate-spin" /> {llmTime && <span className="font-medium text-ink">LLM answered in {llmTime}.</span>} Measuring on the twin and writing the SQL</div>}
        {job.done && !job.error && !job.results && <div className="glass p-5 text-sm text-slate-700">No change worth its cost, so no SQL to apply.</div>}
        {job.done && job.results && (
          <>
            <section className={cn("space-y-2 rounded-3xl bg-rose p-5 text-ink", flash && "fresh-flash")}>
              <h3 className="text-sm font-semibold">Time saved on the twin</h3>
              {job.twin_mode !== "live" && <p className="text-xs text-slate-700">Recorded mode: replayed from an earlier twin run, or estimated from HypoPG costs if this fix was never measured.</p>}
              {job.results.map((t) => <SavedTime key={t.template_id} t={t} label={aiView ? t.template_id : t.label} />)}
              <Source>synthetic {job.rows ? `${job.rows.toLocaleString("en-US")}-row ` : ""}twin, {twinNote(job.twin_mode)}, median of {job.sim?.runs} runs; not production</Source>
            </section>
            {best !== null && <div className={cn("glass p-5", flash && "fresh-flash")}><Gauge value={best} unit="%" label="best speedup on the twin" /></div>}
          </>
        )}
      </div>

      {job.done && job.results && (aiView ? (
        <div className="inset-field p-3 text-sm text-slate-700 md:col-span-12">SQL hidden in the AI view: it holds real names.</div>
      ) : (
        <>
          {([["SQL to apply", job.migration, "migration.sql"], ["Rollback", job.rollback, "rollback.sql"]] as const).map(([title, text, file]) => (
            <section key={file} className={cn("glass min-w-0 p-5 md:col-span-6", flash && "fresh-flash")}>
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

/** The LLM's time for a running question: the recorded seconds on a replay, else poll-accurate. */
function llmTime(run: Running): string | null {
  if (run.replay) return run.replay.seconds != null ? `${run.replay.seconds.toFixed(1)} s (recorded)` : null;
  return run.answeredAt ? `about ${Math.round((run.answeredAt - run.startedAt) / 1000)} s` : null;
}

const TITLE = Object.fromEntries(STAGES.map((x) => [x.id, x.title])) as Record<(typeof STAGES)[number]["id"], string>;

/** The 8 stages of the running question: ticks on the ones reached, the current one pulsing, and
 *  the ai service's progress events beside them. */
function Progress() {
  const run = useContextStore((s) => s.running);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(id); }, []);
  if (!run) return null;
  const last = Math.max(...run.reached.map((x) => ORDER.indexOf(x)));
  return (
    <>
      <section className="rounded-3xl bg-rose p-5 text-ink md:col-span-5">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold">Pipeline progress</h3>
          {run.replay
            ? <span className="text-xs text-slate-700">replay speed, not the real duration</span>
            : <span className="font-mono text-xs text-slate-700">{((now - run.startedAt) / 1000).toFixed(1)} s</span>}
        </div>
        <div className="relative space-y-1.5">
        <div className="absolute bottom-3 left-3 top-3 w-0.5 -translate-x-1/2 rounded-full bg-white/60" aria-hidden>
          <div className="w-full rounded-full bg-ink transition-[height] duration-500 ease-out motion-reduce:transition-none" style={{ height: `${(last / (ORDER.length - 1)) * 100}%` }} />
        </div>
        {ORDER.map((id) => {
          const Icon = STAGE_ICON[id], on = id === run.stage && !run.error, done = run.reached.includes(id) && !on;
          return (
            <div key={id} className={cn("flex items-center gap-2 text-sm", !done && !on && "text-slate-500", on && "animate-pulse font-semibold")}>
              <span className={cn("relative flex size-6 items-center justify-center rounded-full transition-colors duration-300", done ? "bg-ink text-white" : on ? "bg-white" : "bg-rose ring-1 ring-white")}>
                {done ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
              </span>
              {TITLE[id]}
            </div>
          );
        })}
        </div>
      </section>
      <section className="glass min-w-0 p-5 md:col-span-7">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">Events from the AI service</h3>
        {run.events.length ? (
          <ol className="max-h-72 space-y-1 overflow-auto font-mono text-xs text-slate-700">
            {run.events.map((e, k) => <li key={k} className="animate-in fade-in slide-in-from-left-2 duration-300 [overflow-wrap:anywhere] motion-reduce:animate-none">{e}</li>)}
          </ol>
        ) : <p className="text-sm text-slate-600">Question received; waiting for the first tool call.</p>}
      </section>
    </>
  );
}

// Local web container only: rendered when the build sets NEXT_PUBLIC_BT_LOCAL=1. Shows real names
// (dehashed by the gateway on the private side); the toggle shows what the AI side saw. The run
// itself lives in the context store (one poller, src/lib/context.ts), so leaving this page does not
// lose it; once it lands, the new bundle is selected and renders here like any history entry.
export function LiveAsk() {
  const [mode, setMode] = useState<"tune" | "data">("tune");
  return (
    <div className="space-y-3">
      <div className="glass-subtle inline-flex pill p-0.5" role="tablist" aria-label="Question type">
        {([["tune", "Why is it slow?"], ["data", "Ask the data"]] as const).map(([m, text]) => (
          <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={seg(mode === m)}>{text}</button>
        ))}
      </div>
      {mode === "data" ? <DataAsk /> : <TuneAsk />}
    </div>
  );
}

function TuneAsk() {
  const { running, fresh, start, replay } = useContextStore();
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bundle = useBundle();
  const busy = !!running && !running.error;

  const ask = async () => {
    setError(await start(question.trim()));
  };

  const job = running?.job as AskJob | null | undefined;
  const saved = !running && bundle;
  return (
    <Bento>
      <div className="glass space-y-2 p-4 md:col-span-12">
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); void ask(); }}>
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="For example: why is the monthly category report slow?" aria-label="Question" className="min-w-0 flex-1 basis-60" />
          <button type="submit" disabled={!question.trim() || busy} className="inline-flex h-8 items-center gap-1.5 pill bg-ink px-3.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
          </button>
        </form>
        <div className="flex flex-wrap items-center gap-2">
          {running && (
            <div className="glass-subtle inline-flex min-w-0 max-w-full items-center gap-2 pill px-3 py-1 text-xs text-slate-600">
              <span className="shrink-0">{running.replay ? "Replay of a saved run" : "Running"}</span>
              <span className="truncate font-medium text-slate-900">{running.question}</span>
            </div>
          )}
          {saved && (
            <div className={cn("inline-flex min-w-0 max-w-full items-center gap-2 pill px-3 py-1 text-xs text-slate-600", fresh === bundle.id ? "bg-lime" : "glass-subtle")}>
              <span className="shrink-0">{fresh === bundle.id ? "Fresh result" : "From history"}</span>
              <span className="truncate font-medium text-slate-900">{bundle.question}</span>
              <span className="hidden shrink-0 font-mono text-slate-500 sm:inline">{bundle.id}, {new Date(bundle.created_at).toLocaleString("en-GB")}</span>
            </div>
          )}
          {saved && (
            <button type="button" onClick={() => setError(replay())} title="Plays this saved run back step by step; no service is called"
              className="inline-flex h-7 items-center gap-1.5 pill bg-ink px-3 text-sm font-medium text-white hover:bg-slate-800">
              <Play className="size-3.5" /> Replay this run
            </button>
          )}
          {saved && <PageLinks />}
        </div>
        <Source>live, local gateway and AI service; the question stays private, the AI side gets template codes only</Source>
      </div>

      {error && <div className="md:col-span-12"><Bad>{error}</Bad></div>}
      {running?.error && <div className="md:col-span-12"><Bad>The run stopped: {running.error}</Bad></div>}

      {running && <Progress />}
      {running && job?.ask && <Result key={running.qid} job={job} question={running.question} live llmTime={llmTime(running)} />}
      {saved && <Result key={bundle.id} job={bundle.job} question={bundle.question} live={false} flash={fresh === bundle.id} />}
    </Bento>
  );
}
