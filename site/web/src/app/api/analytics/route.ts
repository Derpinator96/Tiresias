import { guard } from "@/lib/ask-server";
import { requireRole } from "@/lib/auth-server";
import { CAN } from "@/lib/auth-shared";
import { analyticsConfig, listEvents } from "@/lib/analytics-server";

// Query events in the dashboard's window, for DBAs only.
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.analytics);
  if (s instanceof Response) return s;
  const cfg = analyticsConfig();
  return Response.json({ config: cfg, now: Date.now(), events: listEvents(Date.now() - cfg.window_minutes * 60_000) });
}
