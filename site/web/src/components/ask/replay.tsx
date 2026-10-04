"use client";
import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Source, Stat } from "@/components/playground/bits";
import { Bento } from "@/components/viz/charts";
import { cn } from "@/lib/utils";
import data from "@/data/ask_replay.json";

// One recorded Ask session, written by scripts/record_ask.py (hashed names only, no question
// text, no dehash). Until a human records one, the file says recorded: false and this shows a
// labelled placeholder.
type Replay = {
  recorded: true;
  recorded_at: string;
  git_commit: string;
  model: string;
  question_id: string;
  template_ids: string[];
  status: string;
  answer: { text: string; numbers: { value: string; tool_call_id: string }[] };
  unmatched: string[];
  events: string[];
  tool_calls: number;
  config: { config_id: string; search: string; actions: Record<string, unknown>[] } | null;
  simulation: { templates: { template_id: string; before_ms: number; after_ms: number; speedup_pct?: number }[]; runs: number; write_ms_delta?: number; storage_mb_delta?: number } | null;
  ledger: { payloads_before: number; payloads_after: number; canary_hits_after: number };
};

const replay = data as unknown as Replay | { recorded: false };
const tag = "inline-flex h-6 items-center pill px-2.5 text-xs";

export function AskReplay() {
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const events = replay.recorded ? replay.events : [];

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setShown((n) => (n >= events.length ? n : n + 1)), 700); // replay pacing only
    return () => clearInterval(t);
  }, [playing, events.length]);
  const stopped = playing && shown >= events.length;
  if (stopped) setPlaying(false);

  if (!replay.recorded) {
    return (
      <div className="glass rounded-2xl p-5">
        <span className={cn(tag, "glass-subtle font-mono text-slate-700")}>PLACEHOLDER</span>
        <p className="mt-2 text-sm text-slate-700">No session recorded yet: <code className="font-mono">make record-ask</code> writes one, hashed names only.</p>
      </div>
    );
  }
  const r = replay;
  const sent = r.ledger.payloads_after - r.ledger.payloads_before;
  const ok = r.status === "ok";
  return (
    <Bento>
      <div className="glass min-w-0 p-5 md:col-span-6">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Agent events</h3>
          <button onClick={() => { if (shown >= events.length) setShown(0); setPlaying(!playing); }} className="inline-flex h-7 items-center gap-1 pill bg-ink px-3 text-sm text-white hover:bg-slate-800">
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : shown >= events.length && shown > 0 ? "Replay again" : "Play"}
          </button>
          <button onClick={() => { setPlaying(false); setShown(events.length); }} className="glass-subtle h-7 pill px-3 text-sm text-slate-600 hover:text-ink">Show all</button>
          <span className="text-xs text-slate-600">{shown} of {events.length}</span>
        </div>
        <ol className="inset-field max-h-64 space-y-1 overflow-auto p-3 font-mono text-xs text-slate-800">
          {events.slice(0, shown).map((e, i) => <li key={i}><span className="text-slate-400">{i + 1}</span> {e}</li>)}
          {shown === 0 && <li className="text-slate-500">press Play to step through the {events.length} events</li>}
        </ol>
        <Source>recorded {r.recorded_at}, {r.model}, commit {r.git_commit.slice(0, 12)}; the AI side received {r.question_id} and codes {r.template_ids.join(", ") || "none"} only; pacing is not real timing; {r.tool_calls} tool calls</Source>
      </div>

      <div className="glass min-w-0 p-5 md:col-span-6">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Answer, hashed</h3>
          <span className={cn(tag, ok ? "glass-subtle text-slate-600" : "bg-signal text-white")}>number checker: {r.status}</span>
        </div>
        <p className="inset-field max-h-64 overflow-auto whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{r.answer.text}</p>
        {r.unmatched.length > 0 && <p className="mt-2 flex items-center gap-2 text-xs text-ink"><span className="size-2 shrink-0 rounded-full bg-signal" aria-hidden />Unmatched numbers: {r.unmatched.join(", ")}</p>}
        {r.answer.numbers.length > 0 && (
          <table className="mt-2 w-full text-sm">
            <thead><tr className="text-xs uppercase tracking-wide text-slate-500"><th className="px-3 py-1.5 text-left font-medium">number</th><th className="px-3 text-left font-medium">from tool call</th></tr></thead>
            <tbody className="font-mono text-xs">{r.answer.numbers.map((n, i) => <tr key={i} className="even:bg-[#f6f7f9]"><td className="px-3 py-1">{n.value}</td><td className="px-3">{n.tool_call_id}</td></tr>)}</tbody>
          </table>
        )}
        <Source>codes as the AI side saw them; the gateway dehashes on the operator side</Source>
      </div>

      {r.simulation ? (
        <div className="glass min-w-0 p-5 md:col-span-8">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Measured on the twin</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {r.simulation.templates.map((t) => (
              <Stat key={t.template_id} label={t.template_id} value={`${t.before_ms.toFixed(1)} to ${t.after_ms.toFixed(1)} ms`} note={`${(100 * (1 - t.after_ms / t.before_ms)).toFixed(1)}% faster, median of ${r.simulation!.runs} runs`} />
            ))}
          </div>
        </div>
      ) : (
        <div className="glass p-5 text-sm text-slate-700 md:col-span-8">No twin measurement in this session.</div>
      )}

      <div className="grid content-start gap-2 md:col-span-4">
        <Stat label="payloads sent this session" value={String(sent)} note="gateway ledger, after minus before" />
        <Stat label="canary hits, all payloads" value={String(r.ledger.canary_hits_after)} note="gateway ledger total after the session" />
      </div>
    </Bento>
  );
}
