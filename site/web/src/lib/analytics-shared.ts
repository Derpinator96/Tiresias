// Query analytics for the local web app: every query a signed-in user runs from the workbench (or
// a data question) is one event with its measured time. A spike is a run at or over the slow
// threshold (config.yaml workload.slow_query_ms). Pure, type imports only (tests/analytics.test.mjs).
import type { Role } from "./auth-shared";

export type QueryEvent = {
  t: number;                // epoch ms when the run finished
  user: string; role: Role;
  label: string;            // the suggestion's name, or "own SQL"
  kind: "slow" | "normal" | "own";
  sql: string;
  ms: number;               // measured by the gateway around the query (connection included)
  rows: number; ok: boolean; error: string | null;
};

export const isSpike = (e: QueryEvent, thresholdMs: number) => e.ok && e.ms >= thresholdMs;

export type Summary = {
  runs: number; perMinute: number; spikes: number; p50: number | null; p95: number | null;
  slowest: QueryEvent | null; byUser: { user: string; runs: number; spikes: number }[];
};

function pct(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1)];
}

/** Tiles for the dashboard over the given events; perMinute counts the last 60 s before `now`. */
export function summarize(events: QueryEvent[], thresholdMs: number, now: number): Summary {
  const ok = events.filter((e) => e.ok);
  const ms = ok.map((e) => e.ms).sort((a, b) => a - b);
  const users = new Map<string, { runs: number; spikes: number }>();
  for (const e of events) {
    const u = users.get(e.user) ?? { runs: 0, spikes: 0 };
    u.runs += 1;
    if (isSpike(e, thresholdMs)) u.spikes += 1;
    users.set(e.user, u);
  }
  return {
    runs: events.length,
    perMinute: events.filter((e) => now - e.t <= 60_000).length,
    spikes: events.filter((e) => isSpike(e, thresholdMs)).length,
    p50: pct(ms, 50), p95: pct(ms, 95),
    slowest: ok.reduce<QueryEvent | null>((a, e) => (!a || e.ms > a.ms ? e : a), null),
    byUser: [...users].map(([user, v]) => ({ user, ...v })).sort((a, b) => b.runs - a.runs),
  };
}
