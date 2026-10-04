import { guard } from "@/lib/ask-server";
import { alertsConfig, session } from "@/lib/auth-server";

export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const s = await session();
  return s ? Response.json({ ...s, inbox_url: alertsConfig().inbox_url }) : Response.json({ error: "not signed in" }, { status: 401 });
}
