"use client";
// Local web app only: the asked question's templates as the real gateway hashed them (from the
// current bundle). In a public build useBundle() is null and only the visualizer renders.
import { useState } from "react";
import { Source } from "@/components/playground/bits";
import { BOX, HashingVisualizer, PILL, useGlitch } from "@/components/hashing/visualizer";
import { useBundle } from "@/lib/context";
import { cn } from "@/lib/utils";

const MISSING_REAL = "not in the bundle's names map";
const MISSING_HASHED = "not in the slow list at ask time";

export function HashingLab() {
  const b = useBundle();
  const [tid, setTid] = useState<string | null>(null);
  const [view, setView] = useState<"real" | "hashed">("real");
  const [shown, play] = useGlitch("");
  const real = (t: string) => b?.names[t] ?? MISSING_REAL;
  const hashed = (t: string) => b?.slow.find((q) => q.template_id === t)?.sql ?? MISSING_HASHED;

  const choose = (t: string) => { setTid(t); setView("hashed"); play(real(t), hashed(t)); };
  const toggle = (v: "real" | "hashed") => {
    if (!tid || v === view) return;
    setView(v);
    if (v === "hashed") play(real(tid), hashed(tid)); else play(hashed(tid), real(tid));
  };

  return (
    <div className="space-y-3">
      {b && (
        <div className="glass p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-slate-900">Your question&apos;s queries</span>
            {tid && (
              <div className="glass-subtle ml-auto flex pill p-0.5">
                {(["real", "hashed"] as const).map((v) => (
                  <button key={v} onClick={() => toggle(v)} className={cn(PILL, view === v ? "bg-ink text-white" : "text-slate-600 hover:bg-white/70")}>{v}</button>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {b.template_ids.map((t) => (
              <button key={t} onClick={() => choose(t)} className={cn(PILL, "font-mono text-xs", tid === t ? "bg-ink text-white" : "glass-subtle text-ink hover:bg-slate-200/70")}>{t}</button>
            ))}
          </div>
          {tid && <pre aria-label="Gateway SQL" className={cn(BOX, "mt-3 bg-(--inset-bg) text-ink")}>{shown}</pre>}
          <Source>bundle {b.id}; real SQL from the bundle&apos;s names map (local only), hashed SQL as the gateway stored it (/v1/templates/slow at ask time). The gateway&apos;s codes use the .env HMAC key, the box below a demo key, so codes differ.</Source>
        </div>
      )}
      <HashingVisualizer />
    </div>
  );
}
