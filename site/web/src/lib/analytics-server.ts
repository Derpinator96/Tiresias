import "server-only";
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { caller, webConfig } from "@/lib/ask-server";
import type { Session } from "@/lib/auth-server";
import type { QueryEvent } from "@/lib/analytics-shared";

// Query events, local web app only: one JSON line per run in BT_HISTORY_DIR/analytics/events.jsonl
// (real SQL inside, so private). The dashboard polls listEvents.

const dir = () => join(process.env.BT_HISTORY_DIR || "./.bt-history", "analytics");
const file = () => join(dir(), "events.jsonl");

export function analyticsConfig(): { poll_ms: number; window_minutes: number; threshold_ms: number } {
  const doc = load(readFileSync(process.env.BT_CONFIG ?? "../../config.yaml", "utf8")) as {
    analytics: { poll_ms: number; window_minutes: number }; workload: { slow_query_ms: number };
  };
  return { ...doc.analytics, threshold_ms: doc.workload.slow_query_ms };
}

export function listEvents(sinceMs: number): QueryEvent[] {
  let text = "";
  try { text = readFileSync(file(), "utf8"); } catch { return []; }
  return text.split("\n").filter(Boolean).map((l) => JSON.parse(l) as QueryEvent).filter((e) => e.t >= sinceMs);
}

/** Runs one SELECT read-only through the gateway (/v1/private/query), records it, returns the result. */
export async function runAndRecord(s: Session, sql: string, label: string, kind: QueryEvent["kind"]) {
  const gateway = caller(process.env.GATEWAY_URL, webConfig().ask_timeout_s);
  const r = await gateway("/v1/private/query", { sql });
  const ok = r.status === 200;
  const e: QueryEvent = {
    t: Date.now(), user: s.email, role: s.role, label, kind, sql,
    ms: ok ? r.body.ms : 0, rows: ok ? r.body.rows.length : 0, ok,
    error: ok ? null : typeof r.body?.detail === "string" ? r.body.detail : `HTTP ${r.status}`,
  };
  if (!existsSync(dir())) mkdirSync(dir(), { recursive: true });
  appendFileSync(file(), JSON.stringify(e) + "\n");
  return { event: e, columns: ok ? r.body.columns : [], rows: ok ? r.body.rows.slice(0, 10) : [], truncated: ok ? r.body.truncated : false };
}
