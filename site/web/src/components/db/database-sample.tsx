"use client";
// /database: one card per pg-prod table from GET /api/db/tables. Every name and number on this
// page arrives from the gateway at runtime; the source holds none.
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorLine, LocalOnly, TH, useJson } from "@/components/db/local";
import { LOCAL } from "@/lib/context";
import { Bento } from "@/components/viz/charts";
import { cn } from "@/lib/utils";

type Col = { name: string; type: string; code: string };
type Tbl = { table: string; code: string; rows: number; size_mb: number; columns: Col[]; sample: unknown[][] };

const ROWS = [5, 10, 25] as const;
const cell = (v: unknown) => (v === null || v === undefined ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function DatabaseSample() {
  const [rows, setRows] = useState<(typeof ROWS)[number]>(5);
  const { data, error, loading } = useJson<Tbl[]>(LOCAL ? `/api/db/tables?rows=${rows}` : null);
  if (!LOCAL) return <LocalOnly />;
  return (
    <div className="mt-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700">
        <span>Sample rows per table</span>
        <div className="glass-subtle flex w-fit pill p-0.5">
          {ROWS.map((n) => (
            <button key={n} type="button" onClick={() => setRows(n)} className={cn("h-7 pill px-3 text-sm", rows === n ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70")}>{n}</button>
          ))}
        </div>
        <span className="text-xs text-slate-500">{loading ? "loading" : data ? `${data.length} tables, /v1/private/tables` : ""}</span>
      </div>
      <ErrorLine text={error} />
      <Bento>
      {data?.map((t) => (
        <section key={t.code} className="glass flex min-w-0 flex-col p-4 md:col-span-6">
          <header className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="min-w-0 truncate font-mono text-base font-semibold text-slate-900">{t.table}</h2>
            <Badge variant="secondary" className="pill font-mono text-xs text-slate-600">{t.code}</Badge>
            <span className="text-xs text-slate-500">{t.rows.toLocaleString()} rows, {t.size_mb.toFixed(1)} MB</span>
          </header>
          <div className="max-h-72 min-w-0 overflow-auto rounded-lg">
            <Table className="text-sm">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {t.columns.map((c) => (
                    <TableHead key={c.code} className={cn(TH, "whitespace-nowrap align-top")}>
                      <div>{c.name} <span className="font-normal">{c.type}</span></div>
                      <div className="font-mono font-normal normal-case tracking-normal text-slate-400">{c.code}</div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {t.sample.map((r, i) => (
                  <TableRow key={i}>{r.map((v, j) => <TableCell key={j} className="max-w-64 truncate py-1 font-mono text-xs" title={cell(v)}>{cell(v)}</TableCell>)}</TableRow>
                ))}
                {!t.sample.length && <TableRow><TableCell colSpan={t.columns.length} className="text-slate-500">no rows</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}
      </Bento>
    </div>
  );
}
