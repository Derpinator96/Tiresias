import "server-only";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import nodemailer from "nodemailer";
import { sqlStatements } from "@/lib/ask-shared";
import { caller, twinModeNow, webConfig } from "@/lib/ask-server";
import { alertsConfig, type Session } from "@/lib/auth-server";
import { alertEmail, type Alert } from "@/lib/alerts-shared";
import { fixesOf } from "@/lib/summary";

// Slow-query alerts, local web app only. The demo trigger picks one of the slow queries already
// in pg-prod's slow log (nothing is reseeded), takes the fix from the recorded search
// (/ai/rl/run, /v1/approve, /v1/simulate/twin), saves the alert under BT_HISTORY_DIR/alerts and
// emails the signed-in DBA through SMTP (Mailpit by default). Alerts hold real names: private.

const dir = () => join(process.env.BT_HISTORY_DIR || "./.bt-history", "alerts");
const ID = /^al_[0-9a-f]{8}$/;

type SlowRow = { template_id: string; sql: string; calls: number; mean_ms: number; total_ms: number; slow: boolean; example: string | null };

/** The fixes in the change set that touch this query: indexes on a table it reads, and a rewrite
 *  only when approve wrote it for this template ("rewrite ... of template q_..."). */
function fixesFor(t: SlowRow, raw: string, migration: string): string[] {
  const tables = new Set([...t.sql.matchAll(/\b(?:FROM|JOIN)\s+"?(\w+)"?/gi)].map((m) => m[1].toLowerCase()));
  const out = fixesOf(migration.replace(/-- rewritten query[\s\S]*$/, "")).filter((f) => [...tables].some((x) => f.includes(`on ${x} (`)));
  if (raw.includes(`of template ${t.template_id}`)) out.push("rewrite this query in the application (a code change)");
  return out;
}

async function send(a: Alert, link: string) {
  const t = nodemailer.createTransport({
    host: process.env.SMTP_HOST || "127.0.0.1", port: Number(process.env.SMTP_PORT || 1025),
    secure: Number(process.env.SMTP_PORT) === 465,
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS ?? "" } : undefined,
  });
  const mail = alertEmail(a, link);
  await t.sendMail({ from: alertsConfig().from, to: a.to, ...mail });
}

export async function createAlert(user: Session, origin: string): Promise<Alert | { error: string }> {
  const s = webConfig().ask_timeout_s;
  const gateway = caller(process.env.GATEWAY_URL, s), ai = caller(process.env.AI_URL, s);
  const log = await gateway("/v1/private/slow-log");
  if (log.status !== 200) return { error: `the gateway did not return the slow log (HTTP ${log.status})` };
  const slow: SlowRow[] = log.body.templates.filter((t: SlowRow) => t.slow);
  if (!slow.length) return { error: "pg-prod's slow log has no slow query yet (run make seed)" };
  const t = slow[Math.floor(Math.random() * slow.length)];

  let migration = "", rollback = "", raw = "", twin: Alert["twin"] = null;
  const rl = await ai("/ai/rl/run", {});
  const config = rl.status === 200 ? rl.body.config : null;
  if (config?.actions?.length) {
    const ap = await gateway("/v1/approve", config);
    if (ap.status === 200) {
      raw = ap.body.files["migration.sql"];
      migration = sqlStatements(raw);
      rollback = sqlStatements(ap.body.files["rollback.sql"]);
    }
    const sim = await gateway("/v1/simulate/twin", config);
    const row = sim.status === 200 ? sim.body.templates.find((x: { template_id: string }) => x.template_id === t.template_id) : null;
    if (row) twin = { before_ms: row.before_ms, after_ms: row.after_ms };
  }

  const a: Alert = {
    id: `al_${randomBytes(4).toString("hex")}`, created_at: new Date().toISOString(), to: user.email,
    template_id: t.template_id, sql: t.sql, example: t.example, calls: t.calls, mean_ms: t.mean_ms, total_ms: t.total_ms,
    threshold_ms: log.body.threshold_ms, fixes: fixesFor(t, raw, migration), migration, rollback, twin,
    twin_mode: twinModeNow(), emailed: false, email_error: null,
  };
  try {
    await send(a, `${origin}/alerts?id=${a.id}`);
    a.emailed = true;
  } catch (e) {
    a.email_error = e instanceof Error ? e.message : String(e);
  }
  if (!existsSync(dir())) mkdirSync(dir(), { recursive: true });
  writeFileSync(join(dir(), `${a.id}.json`), JSON.stringify(a));
  return a;
}

export function listAlerts(email: string): Alert[] {
  let files: string[] = [];
  try { files = readdirSync(dir()); } catch { return []; }
  return files.filter((f) => ID.test(f.replace(/\.json$/, "")))
    .map((f) => readAlert(f.replace(/\.json$/, "")))
    .filter((a): a is Alert => !!a && a.to === email)
    .sort((x, y) => y.created_at.localeCompare(x.created_at));
}

export function readAlert(id: string): Alert | null {
  if (!ID.test(id)) return null;
  try { return JSON.parse(readFileSync(join(dir(), `${id}.json`), "utf8")); } catch { return null; }
}
