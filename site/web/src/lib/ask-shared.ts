// The live Ask flow, ported from dashboard/home.py run_job and dashboard/data.py sql_statements.
// Pure: the gateway and ai calls are passed in, so tests/ask.test.mjs runs it with fakes.
// No imports, so Node's type stripping can load it.

export type Call = (path: string, body?: unknown) => Promise<{ status: number; body: any }>; // eslint-disable-line @typescript-eslint/no-explicit-any

export type TemplateResult = { template_id: string; label: string; before_ms: number; after_ms: number; saved_ms: number; pct: number };

export type AskJob = {
  question_id: string;
  template_ids: string[];
  done: boolean;
  ask?: { status: number; detail?: string; checker?: string; unmatched?: string[]; hashed?: string; real?: string; tool_calls?: number };
  config?: unknown;
  sim?: { runs: number; write_ms_delta?: number; storage_mb_delta?: number } | null;
  results?: TemplateResult[];
  rows?: number | null;
  migration?: string;
  rollback?: string;
  error?: string;
  // Raw pieces kept for the bundle (src/lib/bundle-build.ts); the page never reads them.
  rl?: unknown;                     // /ai/rl/run body when the web ran the search
  files?: Record<string, string>;   // raw /v1/approve files
  ask_body?: unknown;               // raw /ai/ask body (llm, seconds, failovers, events, tool_calls)
  simulation?: unknown;             // raw SimResult
};

/** The runnable SQL in an approve file, without its comments. A rewrite is a suggested code
 *  change, so approve writes it as comments; its query is taken from the block after "Rewritten:". */
export function sqlStatements(text: string): string {
  const out: string[] = [];
  let inRewrite = false;
  for (const line of text.split("\n")) {
    if (line.trim().startsWith("--    Rewritten:")) {
      inRewrite = true;
      out.push("-- rewritten query (application code change)");
      continue;
    }
    if (inRewrite && line.startsWith("--      ")) {
      out.push(line.slice("--      ".length));
      continue;
    }
    inRewrite = false;
    if (line.trim() && !line.trimStart().startsWith("--")) out.push(line);
  }
  return out.join("\n");
}

/** One-line reason from an ai error body (FastAPI detail: a string or the ai service's dict). */
export function errorLine(status: number, body: any): string { // eslint-disable-line @typescript-eslint/no-explicit-any
  const d = body?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object") return d.detail || d.error || JSON.stringify(d);
  return `HTTP ${status} from the ai service`;
}

async function ok(call: Call, path: string, body?: unknown) {
  const r = await call(path, body);
  if (r.status < 200 || r.status >= 300) {
    const d = r.body?.detail;
    throw new Error(`${path}: HTTP ${r.status}${d ? ` (${typeof d === "string" ? d : JSON.stringify(d)})` : ""}`);
  }
  return r.body;
}

/** dashboard/home.py run_job: the agent's answer, then the configuration and twin measurement it
 *  used (or a fresh search and measurement if it made none), then the SQL. Never throws: errors
 *  land in job.error so the page never waits forever. */
export async function runJob(job: AskJob, gateway: Call, ai: Call): Promise<void> {
  try {
    const r = await ai("/ai/ask", { question_id: job.question_id, template_ids: job.template_ids });
    const body = r.body ?? {};
    const good = r.status === 200;
    job.ask_body = body;
    job.ask = good
      ? { status: 200, checker: body.status, unmatched: body.unmatched ?? [], hashed: body.answer?.text ?? "", tool_calls: body.tool_calls }
      : { status: r.status, detail: errorLine(r.status, body) };
    if (good && body.status === "ok" && body.answer?.text) {
      job.ask.real = (await ok(gateway, "/v1/answers/dehash", { question_id: job.question_id, text: body.answer.text, numbers: [] })).text;
    }
    let config = good ? body.config : null;
    let sim = good ? body.simulation : null;
    if (!config || !config.actions?.length) {
      const rl = await ai("/ai/rl/run", {});
      if (rl.status !== 200) throw new Error(`the search failed (HTTP ${rl.status} from the ai service)`);
      config = rl.body.config;
      job.rl = rl.body;
      sim = null;
    }
    job.config = config;
    if (config.actions.length) {
      if (!sim) sim = await ok(gateway, "/v1/simulate/twin", config);
      const files = (await ok(gateway, "/v1/approve", config)).files;
      job.files = files;
      job.migration = sqlStatements(files["migration.sql"]);
      job.rollback = sqlStatements(files["rollback.sql"]);
      const table = config.actions.find((a: { type: string }) => a.type === "add_index")?.table;
      const meta = await ok(gateway, "/v1/meta/tables");
      job.rows = meta.find((t: { table: string }) => t.table === table)?.rows ?? null;
      const shown = sim.templates.filter((t: { template_id: string }) => job.template_ids.includes(t.template_id));
      const list = shown.length ? shown : sim.templates;
      const labels: string[] = (await ok(gateway, "/v1/answers/dehash", { question_id: job.question_id, text: list.map((t: { template_id: string }) => t.template_id).join("\n"), numbers: [] })).text.split("\n");
      job.results = list.map((t: { template_id: string; before_ms: number; after_ms: number }, i: number) => ({
        template_id: t.template_id, label: labels[i] ?? t.template_id, before_ms: t.before_ms, after_ms: t.after_ms,
        saved_ms: t.before_ms - t.after_ms, pct: t.before_ms ? (100 * (t.before_ms - t.after_ms)) / t.before_ms : 0,
      }));
    }
    job.simulation = sim;
    job.sim = sim ? { runs: sim.runs, write_ms_delta: sim.write_ms_delta, storage_mb_delta: sim.storage_mb_delta } : null;
  } catch (e) {
    job.ask ??= { status: 0, detail: "not reached" };
    job.error = e instanceof Error ? e.message : String(e);
  } finally {
    job.done = true;
  }
}
