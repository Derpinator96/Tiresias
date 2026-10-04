// "In plain words": the outcome of one Ask written from the job's own data (twin results, SQL,
// costs, matched templates), never from the LLM, so it reads the same whether or not the LLM's
// answer passed the number checker. Every number here is a field of the job. Pure, no imports
// beyond types (tests/summary.test.mjs).
import type { AskJob } from "./ask-shared";

const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 1 });
/** The SQL of a dehashed label: `query "SELECT ..."` becomes `SELECT ...`. */
export const sqlOf = (label: string) => label.replace(/^query "([\s\S]*)"$/, "$1");

/** Each fix in words, read from the migration SQL that approve wrote. */
export function fixesOf(migration: string): string[] {
  const out: string[] = [];
  for (const m of migration.matchAll(/CREATE INDEX\b[^;]*?\bON\s+"?([\w.]+)"?\s*\(([^)]*)\)/gi)) {
    out.push(`add an index on ${m[1]} (${m[2].replace(/"/g, "").replace(/\s*,\s*/g, ", ")})`);
  }
  if (/rewritten query/i.test(migration)) out.push("rewrite the query in the application (a code change)");
  return out;
}

export type Summary = { verdict: string | null; asked: string[]; outcome: string[] };

const noComments = (sql: string) => sql.replace(/\/\*[\s\S]*?\*\/|--[^\n]*/g, "").trim();   // planted canaries live in comments
/** Tables a query reads, from its FROM and JOIN clauses. */
export const tablesOf = (sql: string) => [...new Set([...noComments(sql).matchAll(/\b(?:FROM|JOIN)\s+"?(\w+)"?/gi)].map((m) => m[1].toLowerCase()))];
/** Tables named in the question (plural or singular). */
const named = (question: string, tables: string[]) =>
  tables.filter((t) => new RegExp(`\\b(${t}|${t.replace(/s$/, "")})\\b`, "i").test(question));
const list = (xs: string[]) => xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`;

/** One line that answers the question first: is what the DBA asked about slow, and where is the time. */
function verdictOf(job: AskJob, question: string): string | null {
  const m = job.matched;
  if (!m?.length) return null;
  const slow = m.filter((x) => x.slow), fast = m.filter((x) => !x.slow);
  const asked = named(question, [...new Set(m.flatMap((x) => tablesOf(x.sql)))]);
  const fixOn = [...new Set([...(job.migration ?? "").matchAll(/CREATE INDEX\b[^;]*?\bON\s+"?(\w+)"?/gi)].map((x) => x[1].toLowerCase()))];
  const fastPart = fast.length ? ` Queries on it alone are fast (${list(fast.map((x) => `${n(x.mean_ms)} ms`))}).` : "";
  if (!slow.length) return `No: nothing you asked about is slow; every matched query runs under ${n(job.threshold_ms ?? 0)} ms, so there is nothing to fix.`;
  const elsewhere = asked.length > 0 && fixOn.length > 0 && !fixOn.some((t) => asked.includes(t));
  if (elsewhere) {
    return `Not ${list(asked)} itself.${fastPart} The slow query joins ${list(asked)} but spends its time reading ${list(fixOn)} (${n(slow[0].mean_ms)} ms on average), so the fix goes on ${list(fixOn)}.`;
  }
  return `Yes: ${slow.length === 1 ? "one query" : `${slow.length} queries`} you asked about ${slow.length === 1 ? "is" : "are"} slow (${list(slow.map((x) => `${n(x.mean_ms)} ms`))} on average).${fastPart} The fix is below.`;
}

export function plainSummary(job: AskJob, question = ""): Summary {
  const verdict = verdictOf(job, question);
  const asked: string[] = [];
  for (const m of job.matched ?? []) {
    const sql = noComments(m.sql);
    const head = `${sql.slice(0, 70)}${sql.length > 70 ? "..." : ""}`;
    asked.push(m.slow
      ? `${head} is slow: ${n(m.mean_ms)} ms on average (slow means ${n(job.threshold_ms ?? 0)} ms or more).`
      : `${head} is not slow: ${n(m.mean_ms)} ms on average, under the ${n(job.threshold_ms ?? 0)} ms threshold, so it needs no fix.`);
  }
  if (job.matched && !job.matched.length) asked.push("The question matched no logged query, so the answer covers the slowest queries overall.");

  const outcome: string[] = [];
  if (job.matched?.length && !job.matched.some((x) => x.slow)) return { verdict, asked, outcome };
  const top = [...(job.results ?? [])].sort((a, b) => b.saved_ms - a.saved_ms)[0];
  if (!job.done) return { verdict, asked, outcome };
  if (!top) {
    outcome.push(job.error ? "The run stopped before a fix was measured." : "No change was worth its cost, so there is nothing to apply.");
    return { verdict, asked, outcome };
  }
  const q = sqlOf(top.label).replace(/\.{3}$/, "");
  outcome.push(`The query to fix is ${q.slice(0, 90)}${q.length > 90 || top.label.includes("...") ? "..." : ""}, ${n(top.before_ms)} ms before the fix.`);
  const fixes = fixesOf(job.migration ?? "");
  if (fixes.length) outcome.push(`The fix: ${fixes.join(", and ")}.`);
  outcome.push(`On the twin it drops to ${n(top.after_ms)} ms, ${Math.round(top.pct)}% faster${job.twin_mode === "live" ? " (measured)" : " (recorded mode: replayed or a HypoPG estimate)"}.`);
  if (job.sim) {
    const parts = [job.sim.storage_mb_delta != null && `${n(job.sim.storage_mb_delta)} MB more on disk`, job.sim.write_ms_delta != null && `+${n(job.sim.write_ms_delta)} ms per insert`].filter(Boolean);
    if (parts.length) outcome.push(`The cost: ${parts.join(" and ")}.`);
  }
  outcome.push("Nothing touches production until you run the SQL below; a rollback script comes with it.");
  return { verdict, asked, outcome };
}
