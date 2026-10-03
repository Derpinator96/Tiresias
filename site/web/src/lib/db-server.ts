import "server-only";
import { readFileSync } from "node:fs";
import { load } from "js-yaml";

// Server side of the local-only /database and /slow-log pages. Same runtime env as ask-server.ts:
// GATEWAY_URL, BT_CONFIG (read-only config.yaml), BT_PLANS_SAMPLE (data/plans/web_sample.json,
// written by scripts/plans_web_sample.py). Responses hold real names: never log them.

export type SlowTemplate = { template_id: string; sql: string; calls: number; mean_ms: number; total_ms: number; slow: boolean; example?: string };
export type BenchEntry = {
  database: string; template_id: string; demo: boolean; sql: string | null; plans: number;
  median_runtime_ms: number | null; max_runtime_ms: number | null; timed_out: number; nodes: number | null; top_ops: string[];
};

function cfg() {
  const doc = load(readFileSync(process.env.BT_CONFIG ?? "../../config.yaml", "utf8")) as { web: { ask_timeout_s: number; slow_log_sample: number } };
  return doc.web;
}

/** GET on the private gateway. `error` is one line for the page; the body is passed through as is. */
export async function gateway<T>(path: string): Promise<{ body: T; error?: undefined } | { body?: undefined; error: string }> {
  const base = (process.env.GATEWAY_URL ?? "").replace(/\/$/, "");
  try {
    const r = await fetch(`${base}${path}`, { signal: AbortSignal.timeout(cfg().ask_timeout_s * 1000), cache: "no-store" });
    if (!r.ok) return { error: `gateway ${path}: HTTP ${r.status}` };
    return { body: (await r.json()) as T };
  } catch (e) {
    return { error: `gateway ${path}: ${e instanceof Error ? e.message : String(e)}` };
  }
}

/** The plan-generation sample, slowest median first (templates without a measured plan last). */
export function benchSample(): { entries: BenchEntry[]; note: string; error?: string } {
  const path = process.env.BT_PLANS_SAMPLE;
  if (!path) return { entries: [], note: "", error: "BT_PLANS_SAMPLE is not set" };
  try {
    const doc = JSON.parse(readFileSync(path, "utf8")) as { entries: BenchEntry[]; note: string };
    const entries = [...doc.entries].sort((a, b) => (b.median_runtime_ms ?? -1) - (a.median_runtime_ms ?? -1));
    return { entries, note: doc.note };
  } catch (e) {
    return { entries: [], note: "", error: `plans sample: ${e instanceof Error ? e.message : String(e)}` };
  }
}

export const slowLogSampleSize = () => cfg().slow_log_sample;
