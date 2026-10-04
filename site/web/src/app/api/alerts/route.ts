import { guard } from "@/lib/ask-server";
import { requireRole } from "@/lib/auth-server";
import { CAN } from "@/lib/auth-shared";
import { createAlert, listAlerts } from "@/lib/alerts-server";

// Slow-query alerts for the signed-in DBA (src/lib/alerts-server.ts).
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.alerts);
  return s instanceof Response ? s : Response.json(listAlerts(s.email));
}

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.alerts);
  if (s instanceof Response) return s;
  const r = await createAlert(s, `http://${req.headers.get("host")}`);   // host already checked by guard
  return Response.json(r, { status: "error" in r ? 502 : 200 });
}
