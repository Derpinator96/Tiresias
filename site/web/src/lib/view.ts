"use client";
// The view every page renders from: the current bundle when one is selected (local web app),
// otherwise the run record and the illustrative facts. One hook, one code path.
import { useMemo } from "react";
import { useBundle } from "@/lib/context";
import { CODE, CODES_LABEL, GNN_SERVING, MIGRATION_SQL, Q1_HASHED, ROLLBACK_SQL, WRITE_COST, run } from "@/lib/facts";
import { viewOf, type Fallback, type RunView } from "@/lib/run-view";

export const FALLBACK: Fallback = {
  run, servingLabel: GNN_SERVING, table: CODE.table, columns: [CODE.eq, CODE.range], sql: Q1_HASHED, migration: MIGRATION_SQL, rollback: ROLLBACK_SQL,
  writeCostMs: WRITE_COST.medianMs, writeCostSource: `db/NOTES.md, 2026-10-03, median of ${WRITE_COST.runs} pgbench runs on the twin`, codesLabel: CODES_LABEL,
};

export function useView(): RunView {
  const b = useBundle();
  return useMemo(() => viewOf(b, FALLBACK), [b]);
}
