import { guard } from "@/lib/ask-server";
import { signup } from "@/lib/auth-server";

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const b = await req.json().catch(() => ({}));
  const err = await signup(b.email, b.name, b.password, b.role ?? "dba");
  return err ? Response.json({ error: err }, { status: 400 }) : Response.json({ ok: true });
}
