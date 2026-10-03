"use client";
// /database: one card per pg-prod table from GET /api/db/tables. Every name and number on this
// page arrives from the gateway at runtime; the source holds none.
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorLine, LocalOnly, useJson } from "@/components/db/local";
import { LOCAL } from "@/lib/context";
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
        <div className="glass-subtle flex w-fit rounded-md p-0.5">
          {ROWS.map((n) => (
            <button key={n} type="button" onClick={() => setRows(n)} className={cn("h-7 rounded px-2.5 text-xs", rows === n ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70")}>{n}</button>
          ))}
        </div>
        {loading && <span className="text-xs text-slate-500">loading</span>}
        {data && <span className="text-xs text-slate-500">{data.length} tables from the gateway (/v1/private/tables)</span>}
      </div>
      <ErrorLine text={error} />
      {data?.map((t) => (
        <section key={t.code} className="glass rounded-xl p-4">
          <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="font-mono text-sm font-semibold text-slate-900">{t.table}</h2>
            <Badge variant="outline" className="font-mono text-xs">{t.code}</Badge>
            <span className="text-xs text-slate-600">{t.rows.toLocaleString()} rows, {t.size_mb.toFixed(1)} MB</span>
          </header>
          <div className="inset-field max-h-96 overflow-auto">
            <Table className="text-xs">
              <TableHeader>
                <TableRow>
                  {t.columns.map((c) => (
                    <TableHead key={c.code} className="h-auto whitespace-nowrap py-1.5 align-top">
                      <div className="text-slate-900">{c.name} <span className="font-normal text-slate-500">({c.type})</span></div>
                      <div className="font-mono text-xs font-normal text-slate-400">{c.code}</div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {t.sample.map((r, i) => (
                  <TableRow key={i}>{r.map((v, j) => <TableCell key={j} className="max-w-64 truncate py-1 font-mono" title={cell(v)}>{cell(v)}</TableCell>)}</TableRow>
                ))}
                {!t.sample.length && <TableRow><TableCell colSpan={t.columns.length} className="text-slate-500">no rows</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
        </section>
      ))}
    </div>
  );
}
