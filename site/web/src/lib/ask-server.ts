import "server-only";
import { existsSync, mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { runJob, type AskJob, type Call } from "@/lib/ask-shared";
import { buildBundle } from "@/lib/bundle-build";
import { summarize, type Bundle, type BundleSummary, type LedgerCounts } from "@/lib/bundle";

// Live Ask, local web container only (infra/docker-compose.yml service `web`). Runtime env, never
// inlined at build: BT_LOCAL=1 turns it on; GATEWAY_URL, AI_URL; BT_CONFIG is the read-only
// config.yaml; BT_WEB_HOSTS lists the Host headers accepted (default the published 127.0.0.1 port).
// Job state holds real names: never log it.

type WebCfg = { ask_timeout_s: number; ask_poll_ms: number };

export function webConfig(): WebCfg {
  const doc = load(readFileSync(process.env.BT_CONFIG ?? "../../config.yaml", "utf8")) as { web: WebCfg };
  return doc.web;
}

export const enabled = () => process.env.BT_LOCAL === "1";

/** 404 when not local; 403 on a foreign Host (DNS rebinding, or the ai container calling web:3000)
 *  or a POST that is not JSON (blocks plain cross-site form posts). Null when the request may pass. */
export function guard(req: Request): Response | null {
  if (!enabled()) return new Response(null, { status: 404 });
  const hosts = (process.env.BT_WEB_HOSTS ?? "127.0.0.1:3000,localhost:3000").split(",");
  if (!hosts.includes(req.headers.get("host") ?? "")) return Response.json({ error: "host not allowed" }, { status: 403 });
  if (req.method === "POST" && !(req.headers.get("content-type") ?? "").startsWith("application/json")) {
    return Response.json({ error: "JSON only" }, { status: 403 });
  }
  return null;
}

function caller(base: string | undefined, timeoutS: number): Call {
  return async (path, body) => {
    const r = await fetch(`${(base ?? "").replace(/\/$/, "")}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutS * 1000),
      cache: "no-store",
    });
    let parsed: unknown = null;
    try { parsed = await r.json(); } catch { parsed = { detail: `HTTP ${r.status}` }; }
    return { status: r.status, body: parsed };
  };
}

// One map per server process; on globalThis so dev reloads do not drop it. Lost on restart.
const g = globalThis as unknown as { __btJobs?: Map<string, AskJob>; __btReady?: Set<string> };
const jobs = (g.__btJobs ??= new Map());
const ready = (g.__btReady ??= new Set()); // bundle builds that finished (file written, or job.error says why not)

// ---- history: one JSON bundle per question under BT_HISTORY_DIR (real names inside) ----------
const ID_RE = /^qn_[0-9a-f]{8}$/;
const historyDir = () => process.env.BT_HISTORY_DIR || "./.bt-history";

export function readBundle(id: string): Bundle | null {
  if (!ID_RE.test(id)) return null;
  try { return JSON.parse(readFileSync(join(historyDir(), `${id}.json`), "utf8")); } catch { return null; }
}

export function deleteBundle(id: string): boolean {
  if (!ID_RE.test(id)) return false;
  try { unlinkSync(join(historyDir(), `${id}.json`)); return true; } catch { return false; }
}

export function listBundles(): BundleSummary[] {
  let files: string[] = [];
  try { files = readdirSync(historyDir()); } catch { return []; }
  return files
    .filter((f) => ID_RE.test(f.replace(/\.json$/, "")))
    .map((f) => readBundle(f.replace(/\.json$/, "")))
    .filter((b): b is Bundle => !!b)
    .map(summarize)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

async function finish(job: AskJob, question: string, gateway: Call, ai: Call, before: LedgerCounts) {
  await runJob(job, gateway, ai);
  const bundle = await buildBundle(job, question, gateway, ai, before);
  try {
    mkdirSync(historyDir(), { recursive: true });
    writeFileSync(join(historyDir(), `${job.question_id}.json`), JSON.stringify(bundle));
  } catch (e) {
    job.error ??= `could not save the history file: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    ready.add(job.question_id); // the page stops polling either way; job.error says when the save failed
  }
}

export async function startAsk(question: string): Promise<{ question_id: string } | { error: string; status: number }> {
  const cfg = webConfig();
  const gateway = caller(process.env.GATEWAY_URL, cfg.ask_timeout_s);
  const ai = caller(process.env.AI_URL, cfg.ask_timeout_s);
  const r = await gateway("/v1/ask/resolve", { question });
  if (r.status !== 200) return { error: `the gateway could not resolve the question (HTTP ${r.status})`, status: 502 };
  const job: AskJob = { question_id: r.body.question_id, template_ids: r.body.template_ids, done: false };
  jobs.set(job.question_id, job);
  const before = await gateway("/v1/ledger").then((l) => l.body, () => null);
  const counts: LedgerCounts = {
    outbound_payloads: before?.outbound_payloads ?? 0, outbound_canary_hits: before?.outbound_canary_hits ?? 0,
    outbound_blocked: before?.outbound_blocked ?? 0, canaries_planted: before?.canaries_planted ?? 0,
  };
  void finish(job, question, gateway, ai, counts); // not awaited: the page polls GET
  return { question_id: job.question_id };
}

export async function askState(qid: string) {
  const job = jobs.get(qid);
  if (!job) return null;
  const poll_ms = webConfig().ask_poll_ms;
  // The raw pieces (ask_body, files, rl, simulation) stay server side: the page reads the bundle.
  const { ask_body, files, rl, simulation, ...shown } = job; // eslint-disable-line @typescript-eslint/no-unused-vars
  const bundle_ready = ready.has(qid) || existsSync(join(historyDir(), `${qid}.json`));
  if (job.ask) return { ...shown, bundle_ready, poll_ms, events: [] as string[] };
  const ai = caller(process.env.AI_URL, 10);
  let events: string[] = [];
  try {
    const r = await ai(`/ai/ask/${encodeURIComponent(qid)}/events`);
    if (r.status === 200) events = r.body.events ?? [];
  } catch {
    // progress only; the job itself reports errors
  }
  return { ...shown, bundle_ready, poll_ms, events };
}
