import { guard } from "@/lib/ask-server";
import { gateway } from "@/lib/db-server";

// Table cards for /database (local web app only; 404 in the public deploy).
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const rows = Number(new URL(req.url).searchParams.get("rows") ?? 5);
  if (![5, 10, 25].includes(rows)) return Response.json({ error: "rows must be 5, 10 or 25" }, { status: 400 });
  const r = await gateway<unknown[]>(`/v1/private/tables?rows=${rows}`);
  return r.error ? Response.json({ error: r.error }, { status: 502 }) : Response.json(r.body);
}
