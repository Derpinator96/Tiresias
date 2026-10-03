import { guard } from "@/lib/ask-server";
import { benchSample, gateway, slowLogSampleSize, type SlowTemplate } from "@/lib/db-server";

// pg-prod's slow log plus the slowest plan-generation templates (local web app only). A failing
// source is reported in its own one-line error so the other half still renders.
export async function GET(req: Request) {
  const denied = guard(req);
  if (denied) return denied;
  const log = await gateway<{ threshold_ms: number; templates: SlowTemplate[] }>("/v1/private/slow-log");
  const bench = benchSample();
  return Response.json({
    threshold_ms: log.body?.threshold_ms ?? null,
    templates: log.body?.templates ?? [],
    gateway_error: log.error,
    bench: bench.entries.slice(0, slowLogSampleSize()),
    bench_note: bench.note,
    bench_error: bench.error,
  });
}
