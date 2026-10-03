"use client";
import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Pip, Source, Stat } from "@/components/playground/bits";
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
      <div className="glass rounded-xl p-5">
        <span className="rounded-md border border-slate-300 bg-slate-50/80 px-1.5 py-0.5 font-mono text-xs text-slate-700">PLACEHOLDER</span>
        <p className="mt-2 text-sm text-slate-700">No session recorded yet: <code className="font-mono">make record-ask</code> writes one, hashed names only.</p>
      </div>
    );
  }
  const r = replay;
  const sent = r.ledger.payloads_after - r.ledger.payloads_before;
  return (
    <div className="space-y-4">
      <div className="glass rounded-xl p-5">
        <p className="text-sm text-slate-700">
          Recorded {r.recorded_at}, {r.model}, commit <span className="font-mono">{r.git_commit.slice(0, 12)}</span>. The AI side received <span className="font-mono">{r.question_id}</span> and codes <span className="font-mono">{r.template_ids.join(", ") || "none"}</span> only.
        </p>
      </div>

      <div className="glass rounded-xl p-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Agent events</h3>
          <button onClick={() => { if (shown >= events.length) setShown(0); setPlaying(!playing); }} className="inline-flex h-7 items-center gap-1 rounded-md bg-ink px-2 text-xs text-white hover:bg-slate-800">
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : shown >= events.length && shown > 0 ? "Replay again" : "Play"}
          </button>
          <button onClick={() => { setPlaying(false); setShown(events.length); }} className="glass-subtle h-7 rounded-md px-2 text-xs text-ink hover:bg-white/70">Show all</button>
          <span className="text-xs text-slate-600">{shown} of {events.length}</span>
        </div>
        <ol className="inset-field max-h-64 space-y-1 overflow-auto p-3 font-mono text-xs text-slate-800">
          {events.slice(0, shown).map((e, i) => <li key={i}><span className="text-slate-400">{i + 1}</span> {e}</li>)}
          {shown === 0 && <li className="text-slate-500">press Play to step through the {events.length} events</li>}
        </ol>
        <Source>pacing is not real timing; {r.tool_calls} tool calls</Source>
      </div>

      <div className="glass rounded-xl p-5">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">Answer, hashed</h3>
          <Pip tone={r.status === "ok" ? "ok" : "bad"} /> <span className="text-xs text-slate-700">number checker: {r.status}</span>
        </div>
        <p className="inset-field whitespace-pre-wrap p-3 text-sm leading-relaxed text-slate-800">{r.answer.text}</p>
        {r.unmatched.length > 0 && <p className="mt-2 text-xs font-medium text-signal">Unmatched numbers: {r.unmatched.join(", ")}</p>}
        {r.answer.numbers.length > 0 && (
          <table className="inset-field mt-2 w-full text-xs">
            <thead className="text-slate-600"><tr><th className="px-3 py-1 text-left font-medium">number</th><th className="px-3 text-left font-medium">from tool call</th></tr></thead>
            <tbody className="font-mono">{r.answer.numbers.map((n, i) => <tr key={i} className="border-t border-slate-200/70"><td className="px-3 py-1">{n.value}</td><td className="px-3">{n.tool_call_id}</td></tr>)}</tbody>
          </table>
        )}
        <Source>codes as the AI side saw them; the gateway dehashes on the operator side</Source>
      </div>

      {r.simulation ? (
        <div className="glass rounded-xl p-5">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Measured on the twin</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {r.simulation.templates.map((t) => (
              <Stat key={t.template_id} label={t.template_id} value={`${t.before_ms.toFixed(1)} to ${t.after_ms.toFixed(1)} ms`} note={`${(100 * (1 - t.after_ms / t.before_ms)).toFixed(1)}% faster, median of ${r.simulation!.runs} runs`} />
            ))}
          </div>
        </div>
      ) : (
        <div className="glass rounded-xl p-5 text-sm text-slate-700">No twin measurement in this session.</div>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <Stat label="payloads sent this session" value={String(sent)} note="gateway ledger, after minus before" />
        <Stat label="canary hits, all payloads" value={String(r.ledger.canary_hits_after)} note="gateway ledger total after the session" />
      </div>
    </div>
  );
}
