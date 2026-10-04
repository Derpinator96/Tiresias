"use client";
// "Ask the data": a plain-English question answered from pg-prod (src/lib/data-shared.ts). Local
// web container only: imported by live-ask.tsx, which the public build swaps out (next.config.ts).
import { useEffect, useState } from "react";
import { Database, Loader2, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Source, SqlBlock } from "@/components/playground/bits";
import { Bento } from "@/components/viz/charts";
import type { DataAnswer, DataError } from "@/lib/data-shared";

const EXAMPLES = ["Which product sold the most units?", "Which region had the highest revenue?", "Which payment method is used most?"];
const STEP = { schema: "reading the schema", llm: "the LLM writing SQL", query: "running the SQL" } as const;

/** Error and blocked states: off-white, ink text, one signal dot (the dot is the only colour). */
export function Bad({ children }: { children: React.ReactNode }) {
  return (
    <div className="inset-field flex items-start gap-2 p-3 text-sm text-ink">
      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-signal" aria-hidden /> <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    </div>
  );
}

const cell = (v: unknown) =>
  v === null || v === undefined ? "null" : typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(v);
const label = (c: string) => c.replace(/_/g, " ");

function Waiting({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 250); return () => clearInterval(id); }, []);
  return (
    <div className="glass flex items-center gap-2 p-5 text-sm text-slate-700 md:col-span-12">
      <Loader2 className="size-4 animate-spin" />
      The LLM is writing SQL from the table and column names, then it runs here read-only.
      <span className="ml-auto font-mono text-xs">{((now - since) / 1000).toFixed(1)} s</span>
    </div>
  );
}

function Answer({ r }: { r: DataAnswer }) {
  const top = r.rows[0];
  return (
    <>
      <section className="rounded-3xl bg-ink p-5 text-white md:col-span-4">
        <h3 className="mb-3 text-sm font-semibold text-lime">Top answer</h3>
        {top ? (
          <dl className="space-y-2">
            {r.columns.map((c, i) => (
              <div key={c} className="min-w-0">
                <dt className="text-xs text-white/60">{label(c)}</dt>
                <dd className="truncate font-mono text-2xl font-semibold tracking-tight" title={cell(top[i])}>{cell(top[i])}</dd>
              </div>
            ))}
          </dl>
        ) : <p className="text-sm text-white/80">The query returned no rows.</p>}
      </section>
      <section className="glass min-w-0 space-y-3 p-5 md:col-span-8">
        <h3 className="text-base font-semibold text-slate-900">{r.question}</h3>
        {r.explanation && <p className="text-sm leading-relaxed text-slate-800">{r.explanation}</p>}
        <p className="text-sm text-slate-700">
          {r.rows.length} row{r.rows.length === 1 ? "" : "s"}{r.truncated ? " (first rows only)" : ""}, ran in {r.ms.toFixed(1)} ms
          {r.seconds !== null && <>; the LLM wrote the SQL in {r.seconds.toFixed(1)} s{r.llm && ` (${r.llm.provider}, ${r.llm.model})`}</>}.
        </p>
        <Source>the LLM saw the question plus table and column names and types, never rows or values; the SQL ran read-only as the SELECT-only app role on pg-prod; these results stay on this machine</Source>
      </section>
      <section className="glass min-w-0 p-5 md:col-span-12">
        <h3 className="mb-2 text-base font-semibold text-slate-900">Result</h3>
        <div className="max-h-96 overflow-auto">
          <Table>
            <TableHeader><TableRow>{r.columns.map((c) => <TableHead key={c} className="text-xs uppercase tracking-wide text-slate-500">{label(c)}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {r.rows.map((row, i) => <TableRow key={i}>{row.map((v, j) => <TableCell key={j} className="font-mono text-xs">{cell(v)}</TableCell>)}</TableRow>)}
            </TableBody>
          </Table>
        </div>
      </section>
      <section className="glass min-w-0 p-5 md:col-span-12">
        <h3 className="mb-2 text-base font-semibold text-slate-900">SQL the LLM wrote</h3>
        <SqlBlock text={r.sql} file="question.sql" />
      </section>
    </>
  );
}

export function DataAsk() {
  const [q, setQ] = useState("");
  const [since, setSince] = useState<number | null>(null);
  const [res, setRes] = useState<DataAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const ask = async (question: string) => {
    if (!question.trim() || since) return;
    setQ(question);
    setSince(Date.now());
    setErr(null);
    try {
      const r = await fetch("/api/data", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: question.trim() }) });
      const body = (await r.json()) as DataAnswer | DataError | { error: string };
      if ("step" in body) setErr(`Stopped at ${STEP[body.step]}: ${body.error}`);
      else if ("error" in body) setErr(body.error);
      else setRes(body);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
    setSince(null);
  };

  return (
    <Bento>
      <div className="glass space-y-2 p-4 md:col-span-12">
        <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); void ask(q); }}>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: which product sold the most units?" aria-label="Question about the data" className="min-w-0 flex-1 basis-60" />
          <button type="submit" disabled={!q.trim() || !!since} className="inline-flex h-8 items-center gap-1.5 pill bg-ink px-3.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40">
            {since ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Ask
          </button>
        </form>
        <div className="flex flex-wrap items-center gap-2">
          <Database className="size-3.5 text-slate-500" aria-hidden />
          {EXAMPLES.map((x) => (
            <button key={x} type="button" disabled={!!since} onClick={() => void ask(x)} className="glass-subtle inline-flex h-7 items-center pill px-3 text-sm text-slate-600 hover:text-ink disabled:opacity-40">{x}</button>
          ))}
        </div>
      </div>
      {since && <Waiting since={since} />}
      {err && <div className="md:col-span-12"><Bad>{err}</Bad></div>}
      {res && !since && <Answer key={res.question + res.ms} r={res} />}
    </Bento>
  );
}
