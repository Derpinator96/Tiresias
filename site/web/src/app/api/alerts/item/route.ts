import { guard } from "@/lib/ask-server";
import { requireRole } from "@/lib/auth-server";
import { CAN } from "@/lib/auth-shared";
import { readAlert } from "@/lib/alerts-server";

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await requireRole(CAN.alerts);
  if (s instanceof Response) return s;
  const a = readAlert(new URL(req.url).searchParams.get("id") ?? "");
  return a && a.to === s.email ? Response.json(a) : Response.json({ error: "no such alert" }, { status: 404 });
}
