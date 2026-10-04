// One flat view of "the run the pages render": the current bundle (an asked question and
// everything the pipeline produced for it) or, with no bundle, the committed run record plus the
// illustrative facts. Every page reads this one object, so there is one code path for both.
// Pure and import-free (type imports only): tests/run-view.test.mjs loads it with Node's type
// stripping and passes the run record in as `fb.run`.
import type { Bundle } from "./bundle";

export type RunRecord = {
  run_id: string; finished_at: string;
  dataset: { hero_table_rows: number; hero_table_size_mb: number };
  q1: { mean_ms_before: number; slow_threshold_ms: number };
  twin: { before_ms: number; after_ms: number; speedup_pct: number; storage_mb: number; runs: number; checksum_match: boolean };
  search: { label: string; predicted_before_ms: number; predicted_after_ms: number; estimator_label: string; recommended_columns: number };
  privacy: { payloads: number; llm_payloads: number; canary_hits: number; canaries_planted: number };
  llm: { provider: string; model: string; tool_calls: number; numbers_checked: number };
};

/** What the public build shows: the run record and the hand-written facts (src/lib/facts.ts). */
export type Fallback = {
  run: RunRecord;
  servingLabel?: string;              // the estimator serving now, when it differs from the run record's
  table: string; columns: string[];   // the illustrative codes of the Q1 index
  sql: string;                        // Q1 as the AI side receives it
  migration: string; rollback: string;
  writeCostMs: number; writeCostSource: string;
  codesLabel: string;
};

export type RunView = {
  id: string;
  live: boolean;                        // true when a bundle is current
  question: string | null; askedAt: string | null;
  templateId: string | null;            // first resolved template (hashed code)
  templateSql: string;                  // hashed, values as ?
  templateSqlReal: string | null;       // real SQL from the bundle's names map; null in a public build
  templates: { id: string; sql: string }[]; // every resolved template with its real SQL
  heroTable: string | null;             // real name when live; the illustrative code otherwise
  heroRows: number | null; heroSizeMb: number | null;
  meanBefore: number | null;            // mean ms of the first resolved template, pg-prod
  slowThresholdMs: number;
  payloads: number; llmPayloads: number | null; canaryHits: number; canariesPlanted: number; blocked: number | null;
  llm: { provider: string; model: string; toolCalls: number | null; seconds: number | null; numbersChecked: number | null; checker: string | null };
  searchLabel: string; estimatorLabel: string;
  predictedBefore: number | null; predictedAfter: number | null;
  twinTag: string | null;               // shown beside twin numbers that may be an estimate
  twinBefore: number | null; twinAfter: number | null; speedupPct: number | null; storageMb: number | null; runs: number | null;
  checksumMatch: boolean; writeCostMs: number;
  recommendedColumns: number; indexCols: string;   // "(col, col)" of the first add_index action
  actions: string[];                    // every chosen action in words, real names when live
  candidates: { table: string; columns: string[]; support: number }[];
  migration: string; rollback: string;
  answer: { real: string; hashed: string } | null;
  events: string[];
  src: { prod: string; twin: string; ledger: string; predicted: string; threshold: string; checksum: string; writeCost: string; sql: string; search: string; llm: string; hero: string };
};

/** Where the twin numbers of an Ask come from, by config.yaml sandbox.twin_mode at ask time.
 *  Bundles saved before the mode was recorded were made in the default recorded mode. */
export function twinNote(mode: string | undefined): string {
  return mode === "live" ? "measured on the twin"
    : "recorded twin mode: replayed from an earlier twin measurement, or estimated from HypoPG costs when this fix was never measured";
}

const nameOf = (b: Bundle, code: string) => b.names[code] ?? code;
/** A column code's real name is "table.column"; the column alone is what an index line shows. */
const colOf = (b: Bundle, code: string) => nameOf(b, code).split(".").pop()!;

export function actionWords(b: Bundle, a: NonNullable<Bundle["config"]>["actions"][number]): string {
  if (a.type === "add_index") return `add index on ${nameOf(b, a.table ?? "?")} (${(a.columns ?? []).map((c) => colOf(b, c)).join(", ")})`;
  if (a.type === "rewrite") return `rewrite ${a.template_id} with rule ${a.rule_id}`;
  if (a.type === "partition") return `partition ${nameOf(b, a.table ?? "?")} by ${colOf(b, a.column ?? "?")}${a.scheme ? ` (${a.scheme})` : ""}`;
  if (a.type === "drop_index") return `drop index on ${nameOf(b, a.table ?? "?")}`;
  return a.type;
}

export function viewOf(b: Bundle | null, fb: Fallback): RunView {
  const r = fb.run;
  if (!b) {
    return {
      id: r.run_id, live: false, question: null, askedAt: null,
      templateId: null, templateSql: fb.sql, templateSqlReal: null, templates: [],
      heroTable: fb.table, heroRows: r.dataset.hero_table_rows, heroSizeMb: r.dataset.hero_table_size_mb,
      meanBefore: r.q1.mean_ms_before, slowThresholdMs: r.q1.slow_threshold_ms,
      payloads: r.privacy.payloads, llmPayloads: r.privacy.llm_payloads, canaryHits: r.privacy.canary_hits, canariesPlanted: r.privacy.canaries_planted, blocked: null,
      llm: { provider: r.llm.provider, model: r.llm.model, toolCalls: r.llm.tool_calls, seconds: null, numbersChecked: r.llm.numbers_checked, checker: null },
      searchLabel: r.search.label,
      estimatorLabel: fb.servingLabel ? `${fb.servingLabel} (serving now; ${r.run_id} predicted with ${r.search.estimator_label.replace(/^estimator:\s*/, "")})` : r.search.estimator_label,
      predictedBefore: r.search.predicted_before_ms, predictedAfter: r.search.predicted_after_ms,
      twinTag: null, twinBefore: r.twin.before_ms, twinAfter: r.twin.after_ms, speedupPct: r.twin.speedup_pct, storageMb: r.twin.storage_mb, runs: r.twin.runs,
      checksumMatch: r.twin.checksum_match, writeCostMs: fb.writeCostMs,
      recommendedColumns: r.search.recommended_columns, indexCols: `(${fb.columns.join(", ")})`,
      actions: [`add index on ${fb.table} (${fb.columns.join(", ")})`],
      candidates: [], migration: fb.migration, rollback: fb.rollback, answer: null, events: [],
      src: {
        prod: `${r.run_id}, pg-prod`, twin: `${r.run_id}, median of ${r.twin.runs} runs on the twin`, ledger: `${r.run_id}, payload ledger`,
        predicted: `${r.run_id}, ${r.search.estimator_label}`, threshold: "config.yaml workload.slow_query_ms, human-approved 2026-10-03",
        checksum: `${r.run_id}, verify/checksum.py on the twin`, writeCost: fb.writeCostSource, sql: fb.codesLabel, search: r.run_id, llm: r.run_id,
        hero: `${r.run_id}; ${fb.codesLabel}`,
      },
    };
  }

  const tid = b.template_ids[0] ?? null;
  const slow = (tid ? b.slow.find((s) => s.template_id === tid) : null) ?? b.slow[0] ?? null;
  const actions = b.config?.actions ?? b.rl?.config.actions ?? [];
  const idx = actions.find((a) => a.type === "add_index");
  const largest = [...b.tables].sort((x, y) => y.rows - x.rows)[0];
  const hero = (idx?.table ? b.tables.find((t) => t.table === idx.table) : null) ?? largest ?? null;
  const simRow = b.sim ? (tid ? b.sim.templates.find((t) => t.template_id === tid) : null) ?? b.sim.templates[0] ?? null : null;
  const speedup = simRow && simRow.before_ms ? (100 * (simRow.before_ms - simRow.after_ms)) / simRow.before_ms : null;
  const bid = `bundle ${b.id}`;
  const hasRl = b.rl !== null;
  const noRl = `${r.run_id} (the bundle has no search run: the agent supplied the configuration)`;
  const writeCost = b.sim?.write_ms_delta ?? null;
  // The ai service sends tool_calls as a list of {tool_call_id, name} (agent/api.py); bundle.ts
  // types it as a number. Both shapes count.
  const tc = (b.llm?.tool_calls ?? b.job.ask?.tool_calls ?? null) as unknown;
  const toolCalls = Array.isArray(tc) ? tc.length : typeof tc === "number" ? tc : null;

  return {
    id: b.id, live: true, question: b.question, askedAt: b.created_at,
    templateId: tid, templateSql: slow?.sql ?? "", templateSqlReal: tid ? (b.names[tid] ?? null) : null,
    templates: b.template_ids.map((id) => ({ id, sql: nameOf(b, id) })),
    heroTable: hero ? nameOf(b, hero.table) : null, heroRows: hero?.rows ?? null, heroSizeMb: hero?.size_mb ?? null,
    meanBefore: slow?.mean_ms ?? null, slowThresholdMs: r.q1.slow_threshold_ms,
    payloads: b.ledger.after.outbound_payloads - b.ledger.before.outbound_payloads, llmPayloads: null,
    canaryHits: b.ledger.after.outbound_canary_hits - b.ledger.before.outbound_canary_hits,
    canariesPlanted: b.ledger.after.canaries_planted, blocked: b.ledger.after.outbound_blocked - b.ledger.before.outbound_blocked,
    llm: {
      provider: b.llm?.provider ?? "none", model: b.llm?.model ?? "none", toolCalls,
      seconds: b.llm?.seconds ?? null, numbersChecked: null, checker: b.job.ask?.checker ?? null,
    },
    searchLabel: b.rl?.label ?? "search: the agent's run_rl tool call (label not in the bundle)",
    estimatorLabel: b.rl?.estimator_label ?? b.estimator?.label ?? r.search.estimator_label,
    predictedBefore: hasRl ? b.rl!.baseline_predicted_ms : r.search.predicted_before_ms,
    predictedAfter: hasRl ? b.rl!.final_predicted_ms : r.search.predicted_after_ms,
    twinTag: b.sim && b.job.twin_mode !== "live" ? "recorded mode: replayed or a HypoPG estimate" : null,
    twinBefore: simRow?.before_ms ?? null, twinAfter: simRow?.after_ms ?? null, speedupPct: speedup,
    storageMb: b.sim?.storage_mb_delta ?? null, runs: b.sim?.runs ?? null,
    checksumMatch: r.twin.checksum_match, writeCostMs: writeCost ?? fb.writeCostMs,
    recommendedColumns: idx?.columns?.length ?? 0, indexCols: idx ? `(${(idx.columns ?? []).map((c) => colOf(b, c)).join(", ")})` : "none",
    actions: actions.map((a) => actionWords(b, a)),
    candidates: (b.mine?.candidates ?? []).map((c) => ({ table: nameOf(b, c.table), columns: c.columns.map((x) => colOf(b, x)), support: c.support })),
    migration: b.job.migration ?? "", rollback: b.job.rollback ?? "",
    answer: b.job.ask?.hashed ? { real: b.job.ask.real ?? b.job.ask.hashed, hashed: b.job.ask.hashed } : null,
    events: b.events,
    src: {
      prod: `${bid}, pg_stat_statements on pg-prod at ask time`,
      twin: b.sim ? `${bid}, ${twinNote(b.job.twin_mode)}, median of ${b.sim.runs} runs` : `${bid}: no twin measurement`,
      ledger: `${bid}, gateway ledger counts after minus before the question`,
      predicted: hasRl ? `${bid}, ${b.rl!.estimator_label}` : noRl,
      threshold: `config.yaml workload.slow_query_ms (not in the bundle)`,
      checksum: `${r.run_id} (checksum_match is not in the bundle)`,
      writeCost: writeCost === null ? `${fb.writeCostSource} (not in the bundle)`
        : b.job.twin_mode === "live" ? `${bid}, pgbench on the twin` : `${bid}, pgbench on the twin if replayed, else the assumed per-index write penalty`,
      sql: `${bid}, real names from the gateway (local only)`, search: hasRl ? bid : noRl, llm: `${bid}, /ai/ask`,
      hero: hero ? `${bid}, /v1/meta/tables (rounded)` : `${bid}: no table metadata`,
    },
  };
}
