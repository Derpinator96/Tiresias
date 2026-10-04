"use client";
import { useEffect, useRef, useState } from "react";
import { Columns3, Eraser, Play, RotateCcw, Table, Variable } from "lucide-react";
import { glitchFrame } from "@/lib/glitch";
import { hashSteps, newKey, type HashStep } from "@/lib/hashing";
import { cn } from "@/lib/utils";

// One fixed neutral example: public pages never show the demo database's real names.
const EXAMPLE = "SELECT SUM(total) FROM invoices WHERE branch = 7 AND issued_on >= '2026-09-26' -- weekly report";
const RAIL = [["comments", Eraser], ["values", Variable], ["tables", Table], ["columns", Columns3]] as const;
const STEP_MS = 1200; // per step: highlight, glitch, rest
const HIGHLIGHT_MS = 400;
const GLITCH_MS = 600;
const TOTAL = STEP_MS * RAIL.length;

/** Seeded so a render stays pure: the same elapsed time gives the same scramble. */
const seeded = (seed: number) => () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);

export function HashingVisualizer() {
  const [steps, setSteps] = useState<HashStep[] | null>(null);
  const [ms, setMs] = useState(-1); // walkthrough time; -1 = not started
  const timer = useRef(0);
  const [reduced, setReduced] = useState(false); // read when play starts: steps swap without glitch

  // Intervals, not requestAnimationFrame, so the walkthrough also advances in a background tab.
  const play = () => {
    clearInterval(timer.current);
    setReduced(matchMedia("(prefers-reduced-motion: reduce)").matches);
    const start = Date.now();
    setMs(0);
    timer.current = window.setInterval(() => {
      const e = Date.now() - start;
      if (e >= TOTAL) clearInterval(timer.current);
      setMs(Math.min(e, TOTAL));
    }, 40);
  };

  // The key exists only in this tab and is made after mount (a prerendered key would mismatch).
  useEffect(() => {
    let auto = 0;
    void hashSteps(EXAMPLE, newKey()).then((s) => { setSteps(s); auto = window.setTimeout(play, 700); });
    return () => { clearTimeout(auto); clearInterval(timer.current); };
  }, []);

  const k = ms < 0 ? 0 : Math.min(RAIL.length, Math.floor(ms / STEP_MS) + 1);
  const local = ms >= TOTAL ? STEP_MS : ms - (k - 1) * STEP_MS;
  const done = ms >= TOTAL;
  const step = steps?.[k];

  let body: React.ReactNode = steps?.[0].text ?? EXAMPLE;
  if (step && k > 0) {
    const rand = seeded(Math.floor(ms));
    const out: React.ReactNode[] = [];
    let pos = 0;
    step.changed.forEach(([a, b], i) => {
      const to = step.text.slice(a, b);
      const t = (local - HIGHLIGHT_MS) / GLITCH_MS;
      const shown = t <= 0 ? step.was[i] : t >= 1 || reduced ? to : glitchFrame(step.was[i], to, t, rand);
      out.push(step.text.slice(pos, a), <span key={i} className={cn("rounded-sm", t < 1 && "bg-peach text-peach-ink")}>{shown}</span>);
      pos = b;
    });
    out.push(step.text.slice(pos));
    body = out;
  }

  return (
    <div className="rounded-3xl bg-peach/40 p-5 shadow-(--glass-shadow)">
      <ol className="flex flex-wrap gap-2" aria-label="Steps">
        {RAIL.map(([label, Icon], i) => {
          const filled = k > i + 1 || (k === i + 1 && local >= HIGHLIGHT_MS + GLITCH_MS);
          return (
            <li key={label} aria-current={k === i + 1 && !done ? "step" : undefined}
              className={cn("inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-xs transition-colors",
                filled ? "bg-peach-ink text-white" : k === i + 1 ? "bg-peach text-ink" : "bg-white/70 text-slate-500")}>
              <Icon className="size-3.5" /> {label}
            </li>
          );
        })}
      </ol>

      <pre aria-label="SQL" className="mt-4 min-h-32 whitespace-pre-wrap break-all rounded-2xl bg-white/85 p-5 font-mono text-lg leading-relaxed text-ink">{body}</pre>
      <div className="sr-only" aria-live="polite">{step?.label}</div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button onClick={play} disabled={!steps || (ms >= 0 && !done)}
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-ink px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50">
          {done ? <><RotateCcw className="size-3.5" /> Replay</> : <><Play className="size-3.5" /> Play</>}
        </button>
        {done && <span className="text-sm text-ink">This is all the AI side sees.</span>}
      </div>
      <p className="mt-3 text-xs text-slate-600">
        codes use a key generated in this tab; SIMPLIFIED: a browser tokenizer, not the gateway&apos;s sqlglot parse
      </p>
    </div>
  );
}
