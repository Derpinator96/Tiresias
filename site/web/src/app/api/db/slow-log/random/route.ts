import { guard } from "@/lib/ask-server";
import { benchSample, gateway, type SlowTemplate } from "@/lib/db-server";

// One random query: pg-prod's slow log or the plan-generation sample, chosen with probability
// proportional to the two pool sizes (the gateway list is fetched for its length). When one
// source fails the other is used alone; when both fail the error is one line.
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const bench = benchSample().entries;
  const log = await gateway<{ templates: SlowTemplate[] }>("/v1/private/slow-log");
  const nProd = log.body?.templates.length ?? 0;
  const total = nProd + bench.length;
  if (!total) return Response.json({ error: log.error ?? "no queries in either pool" }, { status: 502 });
  if (Math.random() * total < nProd) {
    const r = await gateway<SlowTemplate>("/v1/private/slow-log/random");
    if (!r.error) return Response.json({ source: "pg-prod", pool: { "pg-prod": nProd, bench: bench.length }, ...r.body });
    if (!bench.length) return Response.json({ error: r.error }, { status: 502 });
  }
  return Response.json({ source: "bench", pool: { "pg-prod": nProd, bench: bench.length }, ...bench[Math.floor(Math.random() * bench.length)] });
}
