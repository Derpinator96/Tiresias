// Data questions ("which product sold the most?"), local web app only. The schema (names and
// types, no rows) goes to the ai service, which has the LLM write one SELECT; the gateway runs it
// read-only on the private side and the rows come back here only. Pure: calls are passed in, so
// tests/data.test.mjs runs it with fakes. No imports beyond types, so Node's type stripping loads it.
import type { Call } from "./ask-shared";

export type DataAnswer = {
  question: string; explanation: string; sql: string; columns: string[]; rows: unknown[][];
  truncated: boolean; ms: number; seconds: number | null; llm: { provider: string; model: string } | null;
};
export type DataError = { error: string; step: "schema" | "llm" | "query" };

const detail = (r: { status: number; body: any }) => // eslint-disable-line @typescript-eslint/no-explicit-any
  typeof r.body?.detail === "string" ? r.body.detail : r.body?.detail?.detail ?? r.body?.detail?.error ?? r.body?.error ?? `HTTP ${r.status}`;

export async function runData(question: string, gateway: Call, ai: Call): Promise<DataAnswer | DataError> {
  const t = await gateway("/v1/private/tables?rows=0");
  if (t.status !== 200) return { error: detail(t), step: "schema" };
  const schema = (t.body as { table: string; columns: { name: string; type: string }[] }[])
    .map((x) => ({ table: x.table, columns: x.columns.map((c) => ({ name: c.name, type: c.type })) }));
  const s = await ai("/ai/sql", { question, schema });
  if (s.status !== 200) return { error: detail(s), step: "llm" };
  if (!s.body.sql) return { error: s.body.explanation || "the LLM returned no SQL", step: "llm" };
  const q = await gateway("/v1/private/query", { sql: s.body.sql });
  if (q.status !== 200) return { error: `${detail(q)} (SQL: ${s.body.sql})`, step: "query" };
  return { question, explanation: s.body.explanation, sql: q.body.sql, columns: q.body.columns, rows: q.body.rows,
    truncated: q.body.truncated, ms: q.body.ms, seconds: s.body.seconds ?? null, llm: s.body.llm ?? null };
}
