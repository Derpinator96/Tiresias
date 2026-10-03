import { deleteBundle, guard, readBundle } from "@/lib/ask-server";

// One saved bundle (src/lib/bundle.ts), real names inside: local web container only.
type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: Request, { params }: Ctx) {
  const denied = guard(req);
  if (denied) return denied;
  const b = readBundle((await params).id);
  return b ? Response.json(b) : Response.json({ error: "no such question" }, { status: 404 });
}

export async function DELETE(req: Request, { params }: Ctx) {
  const denied = guard(req);
  if (denied) return denied;
  return deleteBundle((await params).id) ? new Response(null, { status: 204 }) : Response.json({ error: "no such question" }, { status: 404 });
}
