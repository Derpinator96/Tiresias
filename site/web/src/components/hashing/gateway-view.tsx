"use client";
// Local web app only: the asked question's templates as the real gateway hashed them (from the
// current bundle). In a public build useBundle() is null and nothing renders.
import { useState } from "react";
import { ArrowDown } from "lucide-react";
import { Source, SqlBlock } from "@/components/playground/bits";
import { HashingVisualizer } from "@/components/hashing/visualizer";
import { name, useBundle } from "@/lib/context";

const TH = "px-2 py-1.5 text-xs font-medium uppercase tracking-wide text-slate-500";

export function HashingLab() {
  const b = useBundle();
  const [load, setLoad] = useState<{ sql: string; n: number } | null>(null);
  return (
    <div className="space-y-6">
      {b && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Your question&apos;s queries, as hashed</h2>
          <Source>bundle {b.id}; the gateway&apos;s codes use the .env HMAC key, the visualizer a demo key made in this tab, so codes differ</Source>
          {b.template_ids.map((tid) => {
            const q = b.slow.find((t) => t.template_id === tid);
            const real = b.names[tid];
            return (
              <div key={tid} className="glass space-y-3 rounded-2xl p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-slate-900">{tid}</span>
                  {q && <span className="text-xs text-slate-600">{q.calls} calls, mean {q.mean_ms.toFixed(1)} ms</span>}
                  {real && (
                    <button onClick={() => setLoad({ sql: real, n: (load?.n ?? 0) + 1 })} className="ml-auto inline-flex h-7 items-center gap-1 pill bg-ink px-3 text-sm text-white hover:bg-slate-800">
                      <ArrowDown className="size-3.5" /> Load into the visualizer
                    </button>
                  )}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="min-w-0"><div className="mb-1 text-xs text-slate-600">Operator view, real SQL</div><SqlBlock text={real ?? "not in the bundle's names map"} /></div>
                  <div className="min-w-0"><div className="mb-1 text-xs text-slate-600">AI side, /v1/templates/slow</div><SqlBlock text={q?.sql ?? "not in the slow list at ask time"} /></div>
                </div>
                {q && q.columns.length > 0 && (
                  <div className="overflow-x-auto rounded-lg">
                    <table className="w-full min-w-[560px] text-left text-sm">
                      <thead><tr><th className={TH}>role</th><th className={TH}>table.column</th><th className={TH}>code</th><th className={TH}>table code</th><th className={TH}>table</th></tr></thead>
                      <tbody className="font-mono text-xs">
                        {q.columns.map((c, i) => (
                          <tr key={i} className="even:bg-[#f6f7f9]">
                            <td className="px-2 py-1.5 text-slate-600">{c.role}</td><td className="px-2 text-slate-900">{name(b, c.col)}</td><td className="px-2">{c.col}</td><td className="px-2">{c.table}</td><td className="px-2 text-slate-900">{name(b, c.table)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Source>as stored by gateway/strip.py and gateway/hashing.py; real names from the bundle, local only</Source>
              </div>
            );
          })}
        </section>
      )}
      <HashingVisualizer key={load?.n ?? 0} initialSql={load?.sql} />
    </div>
  );
}
