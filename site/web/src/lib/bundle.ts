// One asked question and everything the pipeline produced for it. Built by src/lib/ask-server.ts
// after the live Ask job finishes, saved under BT_HISTORY_DIR, served by /api/history. Every page
// of the local web app renders from the current bundle (src/lib/context.ts) when one is selected.
// Private: holds real names (the `names` map), so it exists only in the local web container.
// No imports, so Node's type stripping can load it in tests.
import type { AskJob } from "./ask-shared";

export type HashedQuery = {
  template_id: string; sql: string; calls: number; mean_ms: number; total_ms: number;
  columns: { table: string; col: string; role: string }[];
};

export type PlanNode = {
  node_id: number; parent_id: number | null; op: string; est_rows: number; est_cost: number; width: number;
  relation?: string; index?: string; filter_cols?: string[]; filter?: string; filter_redacted?: boolean;
  actual_rows?: number; rows_removed?: number; self_ms?: number;
};
export type HashedPlan = { plan_id: string; template_id: string; setup_id: string; source: string; nodes: PlanNode[] };
export type Prediction = { plan_id: string; estimator: string; total_ms: number; nodes: { node_id: number; self_ms: number; share: number }[] };
export type Explain = {
  estimator: string; label: string; predicted_total_ms: number;
  top_nodes: { node_id: number; op: string; relation?: string | null; predicted_share_pct: number; predicted_self_ms: number }[];
  misestimate_alert_ratio: number;
  misestimates: { node_id: number; op: string; relation?: string | null; est_rows: number; actual_rows: number; ratio: number; recommend: string }[];
};

export type Action = { type: string; table?: string; columns?: string[]; template_id?: string; rule_id?: string; column?: string; scheme?: string; contribution?: number; cand_id?: string };
export type Config = { config_id: string; search: string; actions: Action[] };
export type SimResult = { config_id: string; source: string; templates: { template_id: string; before_ms: number; after_ms: number }[]; write_ms_delta: number | null; storage_mb_delta: number; runs: number };
export type Candidate = { cand_id: string; table: string; columns: string[]; support: number; evidence: { items: string[]; templates: string[] } };
export type TableMeta = { table: string; rows: number; size_mb: number; writes_per_s: number };
export type LedgerCounts = { outbound_payloads: number; outbound_canary_hits: number; outbound_blocked: number; canaries_planted: number };

/** /ai/rl/run as returned by the ai service (agent/api.py ai_rl_run); null when the agent's own
 *  run_rl tool call supplied the config and the web ran no search itself. */
export type RlRun = {
  config: Config; label: string; estimator_label: string; baseline_predicted_ms: number; final_predicted_ms: number;
  steps: number; configs_costed: number; cache_hits: number; episodes: number;
  top_configs: Record<string, unknown>[]; greedy: Record<string, unknown> | null; rewrites: Record<string, unknown>[];
  final_choice: string; partition: unknown; q_entries: number;
};

export type Bundle = {
  id: string;                       // the gateway's question_id
  question: string;
  created_at: string;               // ISO 8601, UTC
  template_ids: string[];           // what the gateway resolved the question to (hashed codes)
  job: AskJob;                      // the Ask result exactly as the Ask page shows it
  events: string[];                 // /ai/ask progress events (one per tool call or failover)
  // tool_calls is the ai service's list of {tool_call_id, name}; older code counted it as a number.
  llm: { provider: string; model: string; seconds?: number; tool_calls?: number | { tool_call_id: string; name: string }[]; failovers?: unknown[] } | null;
  estimator: { estimator: string; label: string } | null;
  slow: HashedQuery[];              // /v1/templates/slow at ask time
  plans: Record<string, HashedPlan[]>;          // template_id -> logged plans, newest first
  predictions: Record<string, Prediction | null>; // template_id -> serving estimator's prediction for plans[tid][0]
  explain: Record<string, Explain | null>;        // template_id -> /ai/gnn/explain
  mine: { candidates: Candidate[]; [k: string]: unknown } | null;   // /ai/mine
  rl: RlRun | null;
  config: Config | null;
  sim: SimResult | null;
  hypopg: { plans: HashedPlan[]; index_storage_mb: number } | null;  // /v1/simulate/hypopg for config
  ledger: { before: LedgerCounts; after: LedgerCounts };
  tables: TableMeta[];              // /v1/meta/tables (hashed)
  names: Record<string, string>;    // code -> real name: t_ tables, c_ "table.column", q_ full real SQL
};

export type BundleSummary = { id: string; question: string; created_at: string; template_ids: string[]; ok: boolean; speedup_pct: number | null; error: string | null };

export const CODE_RE = /\b[tcq]_[0-9a-f]{8}\b/g;

/** Real names for codes in a text, from a bundle's names map. Unknown codes stay as they are. */
export function dehashWith(names: Record<string, string> | undefined, text: string): string {
  return names ? text.replace(CODE_RE, (c) => names[c] ?? c) : text;
}

/** One line per bundle for the history list. */
export function summarize(b: Bundle): BundleSummary {
  const r = b.job.results?.find((t) => b.template_ids.includes(t.template_id)) ?? b.job.results?.[0];
  return {
    id: b.id, question: b.question, created_at: b.created_at, template_ids: b.template_ids,
    ok: b.job.ask?.status === 200 && b.job.ask?.checker === "ok" && !b.job.error,
    speedup_pct: r ? Math.round(r.pct) : null, error: b.job.error ?? b.job.ask?.detail ?? null,
  };
}
