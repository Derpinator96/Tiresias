import { guard } from "@/lib/ask-server";
import { signout } from "@/lib/auth-server";

export async function POST(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  await signout();
  return Response.json({ ok: true });
}
