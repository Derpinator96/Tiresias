// Builds the Bundle (src/lib/bundle.ts) for one finished Ask job: the job plus everything the
// gateway and ai service know about its templates. Pure: the Call functions are passed in, so
// tests/bundle.test.mjs runs it with fakes. Every enrichment call is best effort: a failure leaves
// that field null or empty, never throws. No runtime imports (Node type stripping loads this file).
import type { AskJob, Call } from "./ask-shared";
import type { Bundle, Config, HashedPlan, LedgerCounts } from "./bundle";

const CODE_RE = /\b[tcq]_[0-9a-f]{8}\b/g; // same as bundle.ts CODE_RE (not imported: no runtime imports here)

/** The 2xx body, or null on any error or non-2xx status. */
async function get<T>(call: Call, path: string, body?: unknown): Promise<T | null> {
  try {
    const r = await call(path, body);
    return r.status >= 200 && r.status < 300 ? (r.body as T) : null;
  } catch {
    return null;
  }
}

function ledgerCounts(b: Record<string, number> | null): LedgerCounts {
  return {
    outbound_payloads: b?.outbound_payloads ?? 0, outbound_canary_hits: b?.outbound_canary_hits ?? 0,
    outbound_blocked: b?.outbound_blocked ?? 0, canaries_planted: b?.canaries_planted ?? 0,
  };
}

/** code -> real name. GET /v1/private/names when the gateway has it; otherwise every code in the
 *  bundle's JSON is dehashed in one /v1/answers/dehash call (q_ codes come back as `query "SQL"`). */
async function names(gateway: Call, qid: string, text: string): Promise<Record<string, string>> {
  const direct = await get<Record<string, string>>(gateway, "/v1/private/names");
  if (direct && typeof direct === "object") return direct;
  const codes = [...new Set(text.match(CODE_RE) ?? [])];
  if (!codes.length) return {};
  const r = await get<{ text: string }>(gateway, "/v1/answers/dehash", { question_id: qid, text: codes.join("\n"), numbers: [] });
  const lines = r?.text?.split("\n") ?? [];
  if (lines.length !== codes.length) return {};
  const out: Record<string, string> = {};
  codes.forEach((c, i) => {
    const real = lines[i].startsWith('query "') && lines[i].endsWith('"') ? lines[i].slice(7, -1) : lines[i];
    if (real !== c) out[c] = real;
  });
  return out;
}

export async function buildBundle(job: AskJob, question: string, gateway: Call, ai: Call, ledgerBefore: LedgerCounts): Promise<Bundle> {
  const askBody = (job.ask_body ?? {}) as { events?: string[]; llm?: { provider: string; model: string }; seconds?: number; tool_calls?: number | unknown[]; failovers?: unknown[] };
  // /ai/ask lists the tool calls ({tool_call_id, name} each); the bundle keeps the count, the raw list stays in job.ask_body.
  const toolCalls = Array.isArray(askBody.tool_calls) ? askBody.tool_calls.length : askBody.tool_calls;
  const config = (job.config as Config | undefined) ?? null;
  const tids = job.template_ids;

  const [estimator, slow, plans, explain, mine, ledgerAfter, tables, hypopg] = await Promise.all([
    get<Bundle["estimator"]>(ai, "/ai/gnn/estimator"),
    get<Bundle["slow"]>(gateway, "/v1/templates/slow"),
    Promise.all(tids.map((t) => get<HashedPlan[]>(gateway, `/v1/templates/${encodeURIComponent(t)}/plans`))),
    Promise.all(tids.map((t) => get<Bundle["explain"][string]>(ai, "/ai/gnn/explain", { template_id: t }))),
    get<Bundle["mine"]>(ai, "/ai/mine", {}),
    get<Record<string, number>>(gateway, "/v1/ledger"),
    get<Bundle["tables"]>(gateway, "/v1/meta/tables"),
    config?.actions?.length ? get<Bundle["hypopg"]>(gateway, "/v1/simulate/hypopg", config) : Promise.resolve(null),
  ]);
  const plansByTid = Object.fromEntries(tids.map((t, i) => [t, plans[i] ?? []]));
  const predictions = Object.fromEntries(await Promise.all(tids.map(async (t) => {
    const p = plansByTid[t][0];
    const r = p ? await get<Bundle["predictions"][string][]>(ai, "/ai/gnn/predict", [p]) : null;
    return [t, r?.[0] ?? null];
  })));

  const b: Bundle = {
    id: job.question_id, question, created_at: new Date().toISOString(), template_ids: tids, job,
    events: askBody.events ?? [],
    llm: askBody.llm ? { ...askBody.llm, seconds: askBody.seconds, tool_calls: toolCalls, failovers: askBody.failovers } : null,
    estimator, slow: slow ?? [], plans: plansByTid, predictions, explain: Object.fromEntries(tids.map((t, i) => [t, explain[i]])),
    mine, rl: (job.rl as Bundle["rl"]) ?? null, config, sim: (job.simulation as Bundle["sim"]) ?? null, hypopg,
    ledger: { before: ledgerBefore, after: ledgerCounts(ledgerAfter) }, tables: tables ?? [], names: {},
  };
  b.names = await names(gateway, job.question_id, JSON.stringify(b));
  return b;
}
