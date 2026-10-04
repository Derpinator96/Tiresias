"use client";
// The current query context: which asked question every page renders from. Local web app only:
// in a public build LOCAL is false, nothing is fetched and useBundle() is always null, so every
// page falls back to its recorded figures. The chosen bundle id lives in localStorage.
import { useEffect } from "react";
import { create } from "zustand";
import { dehashWith, type Bundle, type BundleSummary } from "@/lib/bundle";
import { reached, replayFrames, stageOf, type StageId } from "@/lib/progress";
import { CONFIG } from "@/lib/facts";
// public build: a stub (null), so the live Ask path is not in any client chunk (next.config.ts)
import { askApi } from "bt-ask-api";

export const LOCAL = process.env.NEXT_PUBLIC_BT_LOCAL === "1";
const KEY = "bt.current";

const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const store = (id: string | null) => { try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch { /* private window */ } };

type S = {
  list: BundleSummary[];
  current: Bundle | null;
  loaded: boolean;    // the list was fetched at least once
  loading: boolean;   // a bundle is being fetched
  refresh: () => Promise<void>;
  select: (id: string | null) => Promise<void>;
  /** The question being answered right now, shared by every page (one poller). */
  running: Running | null;
  /** Bundle id of a result that just arrived; cleared after FRESH_MS, drives the "fresh" flash. */
  fresh: string | null;
  start: (question: string) => Promise<string | null>;  // null on success, else the error text
  /** Plays the selected saved bundle back through `running`, with no service call. */
  replay: () => string | null;
};

export type Running = {
  qid: string; question: string; startedAt: number; events: string[];
  stage: StageId; reached: StageId[]; answered: boolean; error: string | null;
  job: Record<string, unknown> | null;   // the polled job state (src/lib/ask-server.ts askState)
  /** Set on a replay of a saved bundle: which one, when it was recorded, its real LLM time. */
  replay?: { id: string; created_at: string; seconds: number | null };
  /** When a poll first saw the answer (live runs; accurate to one poll interval). */
  answeredAt?: number;
};
const FRESH_MS = 6000;

export const useContextStore = create<S>()((set, get) => ({
  list: [], current: null, loaded: false, loading: false, running: null, fresh: null,
  start: async (question) => {
    if (!LOCAL || !askApi) return "live Ask is off in this build";
    if (get().running && !get().running?.error) return "a question is already running";
    let qid: string;
    try {
      const r = await askApi.post(question);
      if (!r.ok) return (r.body.error as string) ?? `HTTP ${r.status}`;
      qid = r.body.question_id as string;
    } catch (e) {
      return e instanceof Error ? e.message : String(e);
    }
    set({ running: { qid, question, startedAt: Date.now(), events: [], stage: "source", reached: ["source"], answered: false, error: null, job: null } });
    const tick = async () => {
      const run = get().running;
      if (!run || run.qid !== qid) return;
      let st: Record<string, unknown> & { events?: string[]; done?: boolean; bundle_ready?: boolean; ask?: unknown; error?: string; poll_ms?: number };
      try {
        const r = await askApi.get(qid);
        st = r.body;
        if (!r.ok) { set({ running: { ...run, error: (st.error as string) ?? `HTTP ${r.status}` } }); return; }
      } catch {
        setTimeout(tick, 2000);
        return;
      }
      // events stop arriving once the answer is back (askState sends []), so keep the last list
      const events = st.events?.length ? st.events : run.events;
      const answered = !!st.ask, done = !!st.done && !!st.bundle_ready;
      set({ running: { ...run, events, answered, job: st, answeredAt: run.answeredAt ?? (answered ? Date.now() : undefined), error: (st.error as string) ?? null,
        stage: stageOf(events, answered, done), reached: [...reached(events, answered, done)] } });
      if (done) {
        await get().refresh();
        await get().select(qid);
        set({ running: null, fresh: qid });
        setTimeout(() => { if (get().fresh === qid) set({ fresh: null }); }, FRESH_MS);
        return;
      }
      setTimeout(tick, typeof st.poll_ms === "number" ? st.poll_ms : 1000);
    };
    void tick();
    return null;
  },
  replay: () => {
    const b = get().current;
    if (!LOCAL || !b) return "no saved question selected";
    if (get().running && !get().running?.error) return "a question is already running";
    const qid = `replay:${b.id}`, frames = replayFrames(b.events);
    const base = { qid, question: b.question, startedAt: Date.now(), error: null,
      replay: { id: b.id, created_at: b.created_at, seconds: b.llm?.seconds ?? null } };
    let k = 0;
    const step = () => {
      if (k > 0 && get().running?.qid !== qid) return;
      const f = frames[k++];
      if (f.done) {
        set({ running: null, fresh: b.id });
        setTimeout(() => { if (get().fresh === b.id) set({ fresh: null }); }, FRESH_MS);
        return;
      }
      set({ running: { ...base, events: f.events, answered: f.answered,
        job: f.answered ? { ...b.job, done: false } : null,
        stage: stageOf(f.events, f.answered, false), reached: [...reached(f.events, f.answered, false)] } });
      setTimeout(step, CONFIG.replayStepMs * (f.answered ? 2 : 1));
    };
    step();
    return null;
  },
  refresh: async () => {
    if (!LOCAL) return;
    try {
      const r = await fetch("/api/history", { cache: "no-store" });
      if (!r.ok) return;
      const list: BundleSummary[] = await r.json();
      set({ list, loaded: true });
      const want = stored() && list.some((b) => b.id === stored()) ? stored() : list[0]?.id ?? null;
      if (want !== (get().current?.id ?? null)) await get().select(want);
    } catch {
      set({ loaded: true });
    }
  },
  select: async (id) => {
    if (!id) { store(null); set({ current: null }); return; }
    set({ loading: true });
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(id)}`, { cache: "no-store" });
      if (r.ok) { store(id); set({ current: await r.json(), loading: false }); return; }
    } catch { /* fall through */ }
    set({ loading: false });
  },
}));

/** The selected bundle, or null (public build, nothing asked yet, or still loading). Fetches the
 *  history once per page load. */
export function useBundle(): Bundle | null {
  const { current, loaded, refresh } = useContextStore();
  useEffect(() => { if (LOCAL && !loaded) void refresh(); }, [loaded, refresh]);
  return LOCAL ? current : null;
}

/** Real name for one code (t_, c_ or q_), or the code itself when the bundle does not know it. */
export const name = (b: Bundle | null, code: string) => b?.names[code] ?? code;

/** Real names for every code in a text. */
export const dehash = (b: Bundle | null, text: string) => dehashWith(b?.names, text);
