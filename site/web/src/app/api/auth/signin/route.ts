import { guard } from "@/lib/ask-server";
import { signin } from "@/lib/auth-server";

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const b = await req.json().catch(() => ({}));
  const err = await signin(b.email, b.password);
  return err ? Response.json({ error: err }, { status: 401 }) : Response.json({ ok: true });
}
