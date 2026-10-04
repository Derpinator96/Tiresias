import { guard } from "@/lib/ask-server";
import { requireRole } from "@/lib/auth-server";
import { CAN } from "@/lib/auth-shared";
import { gateway } from "@/lib/db-server";
import { NORMAL_QUERIES } from "@/lib/workbench-queries";

type Row = { template_id: string; sql: string; mean_ms: number; calls: number; slow: boolean; example: string | null };
const noComments = (sql: string) => sql.replace(/\/\*[\s\S]*?\*\/|--[^\n]*/g, "").trim();

// Slow suggestions: the latest logged literal query of every slow template in pg-prod's log.
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.workbench);
  if (s instanceof Response) return s;
  const log = await gateway<{ threshold_ms: number; templates: Row[] }>("/v1/private/slow-log");
  const slow = (log.body?.templates ?? []).filter((t) => t.slow && t.example)
    .map((t) => ({ id: t.template_id, label: noComments(t.sql).slice(0, 90), sql: noComments(t.example!), mean_ms: t.mean_ms, calls: t.calls }));
  return Response.json({ slow, normal: NORMAL_QUERIES, threshold_ms: log.body?.threshold_ms ?? null, error: log.error ?? null });
}
