import "server-only";
import { readFileSync } from "node:fs";
import { load } from "js-yaml";
import { runJob, type AskJob, type Call } from "@/lib/ask-shared";

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
const g = globalThis as unknown as { __btJobs?: Map<string, AskJob> };
const jobs = (g.__btJobs ??= new Map());

export async function startAsk(question: string): Promise<{ question_id: string } | { error: string; status: number }> {
  const cfg = webConfig();
  const gateway = caller(process.env.GATEWAY_URL, cfg.ask_timeout_s);
  const ai = caller(process.env.AI_URL, cfg.ask_timeout_s);
  const r = await gateway("/v1/ask/resolve", { question });
  if (r.status !== 200) return { error: `the gateway could not resolve the question (HTTP ${r.status})`, status: 502 };
  const job: AskJob = { question_id: r.body.question_id, template_ids: r.body.template_ids, done: false };
  jobs.set(job.question_id, job);
  void runJob(job, gateway, ai); // not awaited: the page polls GET
  return { question_id: job.question_id };
}

export async function askState(qid: string) {
  const job = jobs.get(qid);
  if (!job) return null;
  const poll_ms = webConfig().ask_poll_ms;
  if (job.ask) return { ...job, poll_ms, events: [] as string[] };
  const ai = caller(process.env.AI_URL, 10);
  let events: string[] = [];
  try {
    const r = await ai(`/ai/ask/${encodeURIComponent(qid)}/events`);
    if (r.status === 200) events = r.body.events ?? [];
  } catch {
    // progress only; the job itself reports errors
  }
  return { ...job, poll_ms, events };
}
