import { guard } from "@/lib/ask-server";
import { requireRole } from "@/lib/auth-server";
import { CAN } from "@/lib/auth-shared";
import { runAndRecord } from "@/lib/analytics-server";

// Runs one read-only SELECT for a signed-in workbench user and records it for the analytics dashboard.
export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.workbench);
  if (s instanceof Response) return s;
  const b = await req.json().catch(() => ({}));
  if (typeof b.sql !== "string" || !b.sql.trim() || b.sql.length > 5000) return Response.json({ error: "sql must be 1 to 5000 characters" }, { status: 400 });
  const kind = b.kind === "slow" || b.kind === "normal" ? b.kind : "own";
  const label = typeof b.label === "string" && kind !== "own" ? b.label.slice(0, 120) : "own SQL";
  return Response.json(await runAndRecord(s, b.sql, label, kind));
}
