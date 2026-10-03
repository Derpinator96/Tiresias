"use client";
import { create } from "zustand";
import { run } from "@/lib/facts";

import { STAGES, type StageId } from "@/lib/stages";

export { STAGES, type StageId };
export type Status = "idle" | "running" | "paused" | "completed";
export type LedgerRow = { id: string; time: string; destination: string; sha256: string; count: number; canaryHits: number; verdict: string };

// The run record keeps ledger totals only: 43 outbound payloads, 5 of them to the LLM, so 38 to
// the ai service. Two aggregate rows, no per-payload hashes. Public pages never call the gateway.
export const RECORD_LEDGER: LedgerRow[] = [
  { id: "aggregate", time: run.finished_at, destination: "ai", sha256: "not in run record", count: run.privacy.payloads - run.privacy.llm_payloads, canaryHits: 0, verdict: "allow" },
  { id: "aggregate", time: run.finished_at, destination: "llm", sha256: "not in run record", count: run.privacy.llm_payloads, canaryHits: run.privacy.canary_hits, verdict: "allow" },
];

type State = {
  step: number; // stages completed, 0..8
  status: Status;
  speed: 1 | 2 | 5;
  selected: StageId | null;
  drawerOpen: boolean;
  completedAt: (string | null)[];
  log: { t: string; msg: string }[];
  gates: boolean[]; // DBA pre-flight checks, ticked by the viewer
  authorizedAt: string | null;
  source: string; // what the replay log names: the run record's id, or the current bundle's id (set by the canvas)
  setSource: (id: string) => void;
  toggleGate: (i: number) => void;
  authorize: () => void;
  play: () => void;
  pause: () => void;
  forward: () => void;
  back: () => void;
  reset: () => void;
  setSpeed: (s: 1 | 2 | 5) => void;
  select: (id: StageId | null) => void;
  toggleDrawer: () => void;
};

const now = () => new Date().toLocaleTimeString([], { hour12: false });

export const useRun = create<State>()((set, get) => ({
  step: 0,
  status: "idle",
  speed: 1,
  selected: null,
  drawerOpen: false,
  completedAt: STAGES.map(() => null),
  log: [],
  gates: [false, false, false, false],
  authorizedAt: null,
  source: run.run_id,
  setSource: (source) => set({ source }),
  toggleGate: (i) => set((s) => ({ gates: s.gates.map((g, j) => (j === i ? !g : g)), authorizedAt: null })),
  authorize: () => set((s) => (s.gates.every(Boolean) ? { authorizedAt: now(), log: [...s.log, { t: now(), msg: "deployment authorized in this browser (nothing sent)" }] } : s)),

  play: () => {
    if (get().status === "completed") get().reset();
    set((s) => ({ status: "running", log: [...s.log, { t: now(), msg: `replay started at stage ${s.step + 1}` }] }));
  },
  pause: () => set({ status: "paused" }),
  forward: () =>
    set((s) => {
      if (s.step >= STAGES.length) return s;
      const step = s.step + 1;
      const completedAt = [...s.completedAt];
      completedAt[s.step] = now();
      const done = step === STAGES.length;
      return {
        step,
        completedAt,
        status: done ? "completed" : s.status === "running" ? "running" : "paused",
        log: [...s.log, { t: completedAt[s.step]!, msg: `${STAGES[s.step].title}: replayed from ${s.source}` }],
      };
    }),
  back: () =>
    set((s) => {
      if (s.step === 0) return s;
      const completedAt = [...s.completedAt];
      completedAt[s.step - 1] = null;
      return { step: s.step - 1, completedAt, status: s.step - 1 === 0 ? "idle" : "paused", log: [...s.log, { t: now(), msg: `stepped back to ${STAGES[s.step - 1].title}` }] };
    }),
  reset: () => set({ step: 0, status: "idle", completedAt: STAGES.map(() => null), log: [] }),
  setSpeed: (speed) => set({ speed }),
  select: (selected) => set({ selected, drawerOpen: selected !== null }),
  toggleDrawer: () => set((s) => ({ drawerOpen: !s.drawerOpen, selected: s.selected ?? "source" })),
}));

/** Visual state of stage i, derived from the step machine. */
export function stageState(i: number, step: number, status: Status): "idle" | "processing" | "done" {
  if (i < step) return "done";
  if (i === step && status === "running") return "processing";
  return "idle";
}
