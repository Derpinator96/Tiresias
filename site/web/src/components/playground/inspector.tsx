"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Download, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { CANARIES, CODES_LABEL, CONFIG, QOR_REWRITTEN, QOR_SQL, TOOLS, WRITE_COST, ms } from "@/lib/facts";
import { bellman, speedupPct, tar } from "@/lib/logic";
import type { RunView } from "@/lib/run-view";
import { niceTicks } from "@/lib/spans";
import { RECORD_LEDGER, STAGES, useRun, type LedgerRow, type StageId } from "@/lib/store";
import { useView } from "@/lib/view";
import { CopyButton, Pip, Source, SqlBlock, Stat, save } from "./bits";

const H = ({ children }: { children: React.ReactNode }) => <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-900 first:mt-0">{children}</h3>;
const seg = (on: boolean) => cn("h-7 rounded-full px-3 text-xs", on ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-200/70");
const NA = "not in bundle";
const n = (x: number | null, unit = " ms", digits = 1) => (x === null ? NA : `${x.toFixed(digits)}${unit}`);

// ---- Postgres source -------------------------------------------------------------------
function SourceSheet() {
  const v = useView();
  return (
    <>
      <H>{v.live ? `${v.templateId} is the slow template the question resolved to` : "Q1 is logged as slow on pg-prod"}</H>
      {v.templateSqlReal && <SqlBlock text={v.templateSqlReal} file="real.sql" />}
      {v.templateSqlReal && <Source>real SQL from the bundle&apos;s names map; private side only</Source>}
      <div className={v.templateSqlReal ? "mt-3" : ""}><SqlBlock text={v.templateSql} file="hashed.sql" /></div>
      <Source>as the AI side receives it; {v.src.sql}</Source>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Stat label="mean before" value={n(v.meanBefore)} note={v.src.prod} />
        <Stat label="slow threshold" value={`${v.slowThresholdMs} ms`} note={v.src.threshold} />
        <Stat label="table rows" value={v.heroRows === null ? NA : v.heroRows.toLocaleString("en-US")} note={`${v.heroTable ?? "table unknown"}; ${v.src.hero}`} />
        <Stat label="table size" value={n(v.heroSizeMb, " MB")} note="on disk" />
      </div>
    </>
  );
}

// ---- Gateway ---------------------------------------------------------------------------
function GatewaySheet() {
  const v = useView();
  const ledger: LedgerRow[] = v.live
    ? [{ id: "this question", time: v.askedAt ?? "", destination: "ai+llm", sha256: NA, count: v.payloads, canaryHits: v.canaryHits, verdict: v.blocked ? `blocked ${v.blocked}` : "allow" }]
    : RECORD_LEDGER;
  const [canary, setCanary] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [dest, setDest] = useState<"all" | "ai" | "llm">("all");
  const rows = ledger.filter(
    (r) => (dest === "all" || r.destination.includes(dest)) && `${r.id} ${r.destination} ${r.sha256}`.toLowerCase().includes(q.toLowerCase()),
  );
  const c = canary === null ? null : CANARIES[canary];
  return (
    <>
      <H>{v.canaryHits} of {v.canariesPlanted} canaries left the private network</H>
      <div className="grid grid-cols-4 gap-1.5">
        {CANARIES.map(([id], i) => (
          <button key={i} onClick={() => setCanary(i === canary ? null : i)}
            className={cn("flex items-center gap-1 rounded-full px-2 py-1 font-mono text-xs",
              i === canary ? "bg-ink text-white" : "glass-subtle text-ink hover:bg-slate-200/70")}>
            <Pip tone="ok" /> {id.slice(3)}
          </button>
        ))}
      </div>
      {c ? (
        <div className="inset-field mt-2 space-y-1 p-3 text-xs text-slate-700">
          <div className="font-mono text-slate-900">{c[0]}</div>
          <div>kind: <span className="font-mono">{c[1]}</span></div>
          <div>placement: {c[2]}</div>
          <div className="flex items-center gap-1.5 text-accent"><ShieldCheck className="size-3.5" /> {v.canaryHits} hits in {v.payloads} outbound payloads of {v.id}</div>
          <Source>db/canaries.py: id = first 8 hex of SHA-256 of the value; any 6-character fragment is also blocked</Source>
        </div>
      ) : (
        <Source>hits are totals, not per canary</Source>
      )}

      <H>Sent to the AI side</H>
      <SqlBlock text={v.templateSql} />
      <Source>
        {v.live ? v.src.sql : CODES_LABEL}; t_ or c_ plus the first {CONFIG.hexChars} hex of HMAC-SHA256; values become ?.{" "}
        <Link href="/hashing" className="text-accent underline">Hash your own SQL</Link>
      </Source>

      <H>Outbound ledger</H>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search id, destination or sha256"
          className="inset-field h-8 flex-1 rounded-full px-3 text-xs outline-none focus:ring-2 focus:ring-accent/40" />
        <div className="glass-subtle flex rounded-full p-0.5">
          {(["all", "ai", "llm"] as const).map((d) => <button key={d} className={seg(dest === d)} onClick={() => setDest(d)}>{d}</button>)}
        </div>
      </div>
      <div className="inset-field max-h-64 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-(--inset-bg) text-slate-500">
            <tr><th className="px-2 py-1.5 font-medium">payload</th><th className="px-2 font-medium">to</th><th className="px-2 font-medium">count</th><th className="px-2 font-medium">sha256</th><th className="px-2 font-medium">canary hits</th></tr>
          </thead>
          <tbody className="font-mono text-slate-800">
            {rows.map((r, i) => (
              <tr key={i} className="even:bg-white/60">
                <td className="px-2 py-1.5">{r.id}</td><td className="px-2">{r.destination}</td><td className="px-2">{r.count}</td>
                <td className="max-w-32 truncate px-2" title={r.sha256}>{r.sha256}</td>
                <td className="px-2"><span className="inline-flex items-center gap-1"><Pip tone={r.canaryHits ? "bad" : "ok"} />{r.canaryHits}</span></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={5} className="px-2 py-3 text-center text-slate-400">no rows match</td></tr>}
          </tbody>
        </table>
      </div>
      <Source>{v.live ? `${v.src.ledger}: ${v.payloads} payloads, ${v.canaryHits} canary hits, ${v.blocked ?? 0} blocked; per-payload hashes stay in the gateway` : `run record totals; per-payload ids stay in the operator ledger`}</Source>
    </>
  );
}

// ---- Miner and estimator ---------------------------------------------------------------
function MinerSheet() {
  const v = useView();
  return (
    <>
      <H>{v.live ? `The search chose ${v.recommendedColumns ? "a composite index" : "no index"} for this question` : "The miner proposes one composite index for Q1"}</H>
      <Stat label="recommended index" value={v.indexCols} note={`${v.recommendedColumns} columns on ${v.heroTable ?? "the table"}; FP-Growth, calls x latency; equality column first (30.01% of rows, db/NOTES.md); ${v.live ? v.src.search : CODES_LABEL}`} />
      {v.live ? (
        <>
          <H>{v.candidates.length} candidates mined</H>
          <table className="inset-field w-full text-xs">
            <tbody className="font-mono text-slate-800">
              {v.candidates.map((c, i) => (
                <tr key={i} className="even:bg-white/60"><td className="px-3 py-1.5">{c.table} ({c.columns.join(", ")})</td><td className="px-3 text-right">{c.support.toFixed(3)}</td></tr>
              ))}
              {v.candidates.length === 0 && <tr><td className="px-3 py-2 text-slate-400">/ai/mine gave no candidates for this bundle</td></tr>}
            </tbody>
          </table>
          <Source>/ai/mine at ask time; support = share of slow time; bundle {v.id}, real names, local only</Source>
        </>
      ) : (
        <Source>candidate list and supports not in {v.id}</Source>
      )}
    </>
  );
}

function GnnSheet() {
  const v = useView();
  return (
    <>
      <div className="glass-subtle inline-block rounded-full px-3 py-1 font-mono text-xs text-slate-600">{v.estimatorLabel}</div>
      <H>Predicted times used by the search</H>
      <div className="grid gap-2 sm:grid-cols-2">
        <Stat label="predicted before" value={n(v.predictedBefore)} note={v.src.predicted} />
        <Stat label="predicted after" value={n(v.predictedAfter)} note="same estimator, with the chosen actions" />
      </div>
      <H>GNN reference loop (not serving)</H>
      <table className="inset-field w-full text-xs">
        <tbody className="font-mono text-slate-800">
          {[["GNN", "2.47"], ["Postgres baseline", "2.54"], ["scikit-learn GBT", "1.56"]].map(([k, x]) => (
            <tr key={k} className="even:bg-white/60"><td className="px-3 py-1.5 font-sans text-slate-600">{k}</td><td className="px-3 text-right">{x}</td></tr>
          ))}
        </tbody>
      </table>
      <Source>median q-error on 40 test plans (too small to conclude); weights not delivered, so the Postgres baseline serves</Source>
    </>
  );
}

// ---- RL search -------------------------------------------------------------------------
const ACTIONS = ["add_index", "rewrite", "partition", "STOP"] as const;
const CHOICES = ACTIONS.slice(0, 3);
const STATES = [[], ["add_index"], ["rewrite"], ["partition"], ["add_index", "rewrite"], ["add_index", "partition"], ["rewrite", "partition"], ["add_index", "rewrite", "partition"]] as string[][];
const key = (s: string[]) => `{${s.join(", ")}}`;
const fresh = () => Object.fromEntries(STATES.flatMap((s) => ACTIONS.map((a) => [`${key(s)}|${a}`, CONFIG.qInit])));

function RlSheet() {
  const v = useView();
  const [q, setQ] = useState<Record<string, number>>(fresh);
  const [cell, setCell] = useState<[number, number]>([0, 0]);
  const [reward, setReward] = useState(0.5);
  const [alpha, setAlpha] = useState(CONFIG.alpha);
  const [gamma, setGamma] = useState(CONFIG.gamma);
  const valid = (s: string[], a: string) => a === "STOP" || !s.includes(a);
  const [si, ai] = cell;
  const s = STATES[si];
  const a = ACTIONS[ai];
  const cur = q[`${key(s)}|${a}`];
  // rl/search.py: STOP has target 0; otherwise the best next value over the options left in s'.
  const next = [...s, a].sort((x, y) => CHOICES.indexOf(x as never) - CHOICES.indexOf(y as never));
  const maxNext = a === "STOP" ? 0 : Math.max(...ACTIONS.filter((b) => valid(next, b)).map((b) => q[`${key(next)}|${b}`]));
  const r = a === "STOP" ? 0 : reward;
  const updated = bellman(cur, r, maxNext, alpha, gamma);
  const vals = Object.values(q);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const shade = (x: number) => (hi === lo ? 0.12 : 0.08 + (0.8 * (x - lo)) / (hi - lo));
  const slider = (label: string, x: number, set: (y: number) => void, min: number, max: number, note: string) => (
    <label className="block text-xs text-slate-600">
      <span className="flex justify-between"><span>{label}</span><span className="font-mono text-slate-900">{x.toFixed(2)}</span></span>
      <input type="range" min={min} max={max} step={0.01} value={x} onChange={(e) => set(Number(e.target.value))} className="w-full accent-accent" />
      <Source>{note}</Source>
    </label>
  );
  return (
    <>
      <H>{v.live ? `${v.actions.length} chosen ${v.actions.length === 1 ? "action" : "actions"}` : "Chosen actions"}</H>
      <ul className="inset-field space-y-1 p-3 font-mono text-xs text-slate-800">
        {v.actions.map((x) => <li key={x}>{x}</li>)}
        {v.actions.length === 0 && <li className="text-slate-400">no actions: the search found nothing worth doing</li>}
      </ul>
      <Source>{v.src.search}: {v.searchLabel}; {v.live ? "real names, local only" : "Q-table not in the run record"}</Source>
      <H>Q-table sandbox</H>
      <Source>cells start at config.yaml rl.q_init {CONFIG.qInit.toFixed(1)}; only your updates change them; darker is higher</Source>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full border-separate border-spacing-0.5 text-xs">
          <thead><tr><th className="text-left font-medium text-slate-500">state</th>{ACTIONS.map((x) => <th key={x} className="font-mono font-medium text-slate-500">{x}</th>)}</tr></thead>
          <tbody>
            {STATES.map((st, i) => (
              <tr key={i}>
                <td className="pr-1 font-mono text-slate-600">{key(st)}</td>
                {ACTIONS.map((x, j) => {
                  const val = q[`${key(st)}|${x}`];
                  const ok = valid(st, x);
                  const sh = shade(val);
                  return (
                    <td key={x}>
                      <button disabled={!ok} onClick={() => setCell([i, j])}
                        style={ok ? { backgroundColor: `rgba(37,99,235,${sh})`, color: sh > 0.45 ? "white" : "#0f172a" } : undefined}
                        className={cn("h-7 w-full rounded font-mono", !ok && "cursor-not-allowed bg-slate-100 text-slate-300", si === i && ai === j && "ring-2 ring-accent")}>
                        {ok ? val.toFixed(3) : "n/a"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <H>Bellman update for Q({key(s)}, {a})</H>
      <div className="space-y-3">
        {a !== "STOP" && slider("reward R", reward, setReward, -1, 1, "time drop minus write and storage penalties, at most 1 (rl/NOTES.md); set by you here")}
        {slider("learning rate alpha", alpha, setAlpha, 0, 1, `config.yaml rl.alpha = ${CONFIG.alpha}`)}
        {slider("discount gamma", gamma, setGamma, 0, 1, `config.yaml rl.gamma = ${CONFIG.gamma}`)}
      </div>
      <div className="inset-field mt-3 p-3 font-mono text-xs leading-relaxed text-slate-800">
        <div>Q(s,a) &larr; Q(s,a) + alpha [R + gamma max Q(s&apos;,a&apos;) &minus; Q(s,a)]</div>
        <div className="text-slate-500">s&apos; = {a === "STOP" ? "terminal (STOP: target 0)" : key(next)}</div>
        <div>= {cur.toFixed(3)} + {alpha.toFixed(2)} &times; ({r.toFixed(2)} + {gamma.toFixed(2)} &times; {maxNext.toFixed(3)} &minus; {cur.toFixed(3)})</div>
        <div className="font-semibold text-slate-900">= {updated.toFixed(3)}</div>
      </div>
      <div className="mt-2 flex gap-2">
        <button className="h-8 rounded-full bg-ink px-3 text-xs font-medium text-white hover:bg-slate-800" onClick={() => setQ({ ...q, [`${key(s)}|${a}`]: updated })}>Apply update</button>
        <button className="glass-subtle h-8 rounded-full px-3 text-xs text-ink hover:bg-slate-200/70" onClick={() => setQ(fresh())}>Reset table</button>
      </div>
    </>
  );
}

// ---- LLM -------------------------------------------------------------------------------
function LlmSheet() {
  const v = useView();
  const [open, setOpen] = useState<string | null>(null);
  const [hashed, setHashed] = useState(false);
  const recomputed = v.twinBefore !== null && v.twinAfter !== null ? speedupPct(v.twinBefore, v.twinAfter) : null;
  const checks: [string, string, string, boolean][] = [
    ["faster on the twin", v.speedupPct === null ? NA : `${v.speedupPct.toFixed(1)}%`, recomputed === null ? v.src.twin : `recomputed here: (1 - ${v.twinAfter} / ${v.twinBefore}) x 100 = ${recomputed.toFixed(2)}%`, recomputed === null || v.speedupPct === null || recomputed.toFixed(1) === v.speedupPct.toFixed(1)],
    ["storage", n(v.storageMb, " MB"), v.src.twin, true],
    ["predicted after", n(v.predictedAfter), v.src.predicted, true],
    ["write cost per insert", `+${v.writeCostMs} ms`, v.src.writeCost, true],
  ];
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-3">
        <Stat label="model" value={v.llm.model} note={`${v.llm.provider}; ${v.src.llm}`} />
        <Stat label="tool calls" value={v.llm.toolCalls === null ? NA : String(v.llm.toolCalls)} note={v.llm.seconds === null ? "this run" : `${v.llm.seconds.toFixed(1)} s end to end`} />
        {v.live ? <Stat label="number checker" value={v.llm.checker ?? "not run"} note="agent/number_checker.py: every number in the answer must match a tool result" /> : <Stat label="payloads to LLM" value={String(v.llmPayloads)} note={`${v.canaryHits} canary hits`} />}
      </div>
      {v.answer && (
        <>
          <H>The answer</H>
          <div className="glass-subtle mb-1 flex w-fit rounded-full p-0.5">
            <button className={seg(!hashed)} onClick={() => setHashed(false)}>dehashed</button>
            <button className={seg(hashed)} onClick={() => setHashed(true)}>hashed, as the LLM wrote it</button>
          </div>
          <div className="inset-field whitespace-pre-wrap p-3 text-xs leading-relaxed text-slate-800">{hashed ? v.answer.hashed : v.answer.real}</div>
          <Source>bundle {v.id}; dehashed by the gateway on the private side</Source>
        </>
      )}
      {v.live && (
        <>
          <H>{v.events.length} events from /ai/ask</H>
          <ol className="inset-field max-h-56 space-y-0.5 overflow-y-auto p-3 font-mono text-xs text-slate-700">
            {v.events.map((e, i) => <li key={i}><span className="text-slate-400">{i + 1}</span> {e}</li>)}
            {v.events.length === 0 && <li className="text-slate-400">the ai service recorded no events for this question</li>}
          </ol>
          <Source>one line per tool call, retry or failover (agent/api.py EVENTS)</Source>
        </>
      )}
      <H>The 8 tools</H>
      <Source>{v.live ? `${v.src.llm}: ${v.llm.toolCalls ?? "?"} calls, listed above` : `${v.id}: ${v.llm.toolCalls} calls; order not in the run record`}; declarations from agent/tools.py</Source>
      <div className="mt-2 space-y-1">
        {TOOLS.map((t, i) => (
          <div key={t.name} className="inset-field">
            <button className="flex w-full items-center gap-2 px-3 py-2 text-left" onClick={() => setOpen(open === t.name ? null : t.name)} aria-expanded={open === t.name}>
              <span className="font-mono text-xs text-slate-400">{i + 1}</span>
              <span className="font-mono text-xs text-slate-900">{t.name}</span>
              <ChevronDown className={cn("ml-auto size-3.5 text-slate-400 transition-transform", open === t.name && "rotate-180")} />
            </button>
            {open === t.name && (
              <div className="px-3 pb-2">
                <p className="mb-2 text-xs text-slate-600">{t.description}</p>
                <pre className="overflow-x-auto font-mono text-xs text-slate-800">{JSON.stringify(t.parameters, null, 2)}</pre>
              </div>
            )}
          </div>
        ))}
      </div>
      <H>Number check</H>
      <Source>{v.live ? "the agent's checked numbers are not in the bundle" : `the agent's ${v.llm.numbersChecked} checked numbers are not in the run record`}; this table re-checks this page</Source>
      <table className="inset-field mt-2 w-full text-xs">
        <tbody>
          {checks.map(([k, x, src, ok]) => (
            <tr key={k} className="align-top even:bg-white/60">
              <td className="px-3 py-1.5 text-slate-600">{k}</td>
              <td className="px-2 py-1.5 font-mono text-slate-900">{x}</td>
              <td className="px-2 py-1.5 text-xs text-slate-500">{src}</td>
              <td className="px-2 py-1.5"><Pip tone={ok ? "ok" : "bad"} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ---- Twin ------------------------------------------------------------------------------
function TwinSheet() {
  const v = useView();
  const spans = [
    { k: "prod mean, before", v: v.meanBefore, c: "bg-slate-400", d: `${v.src.prod}; measured on pg-prod` },
    { k: "twin before", v: v.twinBefore, c: "bg-signal", d: v.src.twin },
    { k: "twin after", v: v.twinAfter, c: "bg-accent", d: `${v.src.twin}, with ${v.actions.join("; ") || "no actions"}. ${v.speedupPct === null ? "" : `${v.speedupPct.toFixed(1)}% faster than twin before.`}` },
    { k: "predicted before", v: v.predictedBefore, c: "bg-signal/40", d: v.src.predicted },
    { k: "predicted after", v: v.predictedAfter, c: "bg-accent/40", d: v.src.predicted },
  ].filter((s): s is typeof s & { v: number } => s.v !== null);
  const [hover, setHover] = useState(1);
  const ticks = niceTicks(Math.max(1, ...spans.map((s) => s.v)));
  const max = ticks.at(-1)! || 1;
  const cur = spans[Math.min(hover, spans.length - 1)];
  return (
    <>
      <H>{v.twinBefore === null ? "No twin measurement in this bundle" : `${v.live ? v.templateId : "Q1"} drops from ${ms(v.twinBefore)} to ${ms(v.twinAfter!)} on the twin`}</H>
      <div className="inset-field p-3">
        <div className="mb-1 flex gap-2 font-mono text-xs text-slate-400">
          <span className="w-[36%]">ms</span>
          <div className="flex flex-1 justify-between">{ticks.map((t) => <span key={t}>{t}</span>)}</div>
          <span className="w-16" />
        </div>
        {spans.map((s, i) => (
          <div key={s.k} className={cn("flex cursor-default items-center gap-2 rounded py-1", hover === i && "bg-white/80")}
            onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}>
            <span className="w-[36%] truncate text-xs text-slate-600">{s.k}</span>
            <div className="relative h-4 flex-1 rounded bg-slate-200/50">
              <div className={cn("h-full rounded", s.c)} style={{ width: `${(s.v / max) * 100}%` }} />
            </div>
            <span className="w-16 text-right font-mono text-xs text-slate-800">{ms(s.v)}</span>
          </div>
        ))}
        {cur && (
          <div className="mt-2 text-xs text-slate-700">
            <span className="font-medium">{cur.k}:</span> {cur.d}
            <Source>{v.live ? "per-node times are in the bundle's plans; totals shown here" : "plan node breakdown not in the run record"}</Source>
          </div>
        )}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Stat label="faster" value={v.speedupPct === null ? NA : `${v.speedupPct.toFixed(1)}%`} note={v.src.twin} />
        <Stat label="storage" value={n(v.storageMb, " MB")} note="twin disk" />
        <Stat label="twin fidelity, Q1" value="0.76" note="plan agreement on a loaded machine (db/sandbox/fidelity.py, 2026-10-03); not per question" />
      </div>
      <H>Result checksum</H>
      <div className="inset-field flex items-start gap-3 p-3">
        <span className={cn("mt-0.5 grid size-6 place-items-center rounded-full text-white", v.checksumMatch ? "bg-accent" : "bg-signal")}>
          <ShieldCheck className="size-3.5" />
        </span>
        <div className="text-xs text-slate-700">
          <div className="font-medium text-slate-900">{v.checksumMatch ? "same result with and without the index" : "checksum mismatch"}</div>
          <Source>checksum_match = {String(v.checksumMatch)}; {v.src.checksum}; hash values not kept</Source>
        </div>
      </div>
      <H>Rewrite diff</H>
      <Source>Q1&apos;s fix is an index, so this is the two-region rewrite (rule or_same_column_to_in, Verified by VeriEQL at 5 rows per table, rendered by hand); {CODES_LABEL}</Source>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div className="min-w-0"><div className="mb-1 text-xs text-slate-500">original</div><SqlBlock text={QOR_SQL} tone="del" /></div>
        <div className="min-w-0"><div className="mb-1 text-xs text-slate-500">rewritten</div><SqlBlock text={QOR_REWRITTEN} tone="add" /></div>
      </div>
    </>
  );
}

// ---- DBA -------------------------------------------------------------------------------
const pct = (base: number) => Math.round((WRITE_COST.medianMs / base) * 100);
const gatesOf = (v: RunView): [string, string][] => [
  ["Twin execution verified", v.twinBefore === null ? `${NA} (${v.src.twin})` : `${ms(v.twinBefore)} to ${ms(v.twinAfter!)}, ${v.src.twin}`],
  ["Result checksum identical", `checksum_match = ${v.checksumMatch} (${v.src.checksum})`],
  ["Zero canary leaks", `${v.canaryHits} of ${v.canariesPlanted} in ${v.payloads} payloads (${v.src.ledger})`],
  ["Write cost reviewed", v.live && v.writeCostMs !== WRITE_COST.medianMs ? `+${v.writeCostMs.toFixed(3)} ms per insert (${v.src.writeCost})` : `+${WRITE_COST.medianMs} ms on a ${WRITE_COST.baseLo} to ${WRITE_COST.baseHi} ms insert, ${pct(WRITE_COST.baseHi)}% to ${pct(WRITE_COST.baseLo)}% (db/NOTES.md)`],
];

function DbaSheet() {
  const v = useView();
  const { gates, toggleGate, authorize, authorizedAt } = useRun();
  const ready = gates.every(Boolean);
  const btn = "glass-subtle inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs text-ink hover:bg-slate-200/70";
  return (
    <>
      <Source>{v.live ? `bundle ${v.id}: files from POST /v1/approve, real names, local only` : `rendered from gateway/approve.py's template; ${CODES_LABEL}`}</Source>
      <div className="mt-3 flex flex-wrap gap-2">
        <CopyButton text={v.migration} label="Copy migration" />
        <CopyButton text={v.rollback} label="Copy rollback" />
        <button className={btn} onClick={() => save(`tiresias-patch-${v.id}.tar`, tar({ "migration.sql": v.migration, "rollback.sql": v.rollback }) as BlobPart, "application/x-tar")}>
          <Download className="size-3.5" /> Download patch archive
        </button>
      </div>
      <H>migration.sql</H>
      <SqlBlock text={v.migration || "-- no migration: the search chose no actions"} file="migration.sql" />
      <H>rollback.sql</H>
      <SqlBlock text={v.rollback || "-- no rollback: nothing to undo"} file="rollback.sql" />
      <H>Pre-flight gates</H>
      <div className="space-y-1.5">
        {gatesOf(v).map(([k, ev], i) => (
          <label key={k} className="inset-field flex cursor-pointer items-start gap-2.5 p-2.5">
            <input type="checkbox" checked={gates[i]} onChange={() => toggleGate(i)} className="mt-0.5 size-4 accent-accent" />
            <span className="text-xs"><span className="font-medium text-slate-900">{k}</span><br /><span className="text-slate-500">{ev}</span></span>
          </label>
        ))}
      </div>
      <button disabled={!ready} onClick={authorize}
        className="mt-3 h-9 w-full rounded-full bg-ink text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300">
        {authorizedAt ? `Noted at ${authorizedAt} in this browser; nothing was deployed` : ready ? "Authorize deployment (noted in this browser only)" : `Tick all 4 gates (${gates.filter(Boolean).length} of 4)`}
      </button>
      <Source>recorded in this browser only; the DBA runs migration.sql with psql</Source>
    </>
  );
}

export const SHEETS: Record<StageId, () => React.ReactElement> = {
  source: SourceSheet, gateway: GatewaySheet, miner: MinerSheet, gnn: GnnSheet, rl: RlSheet, llm: LlmSheet, twin: TwinSheet, dba: DbaSheet,
};

export function Inspector() {
  const { selected, drawerOpen, select, toggleDrawer } = useRun();
  const [min, setMin] = useState(false);
  const [wide, setWide] = useState(false);
  const i = STAGES.findIndex((s) => s.id === selected);
  const id = STAGES[Math.max(i, 0)].id;
  const Sheet = SHEETS[id];
  const light = "size-3 rounded-full";
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && drawerOpen && select(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen, select]);
  return (
    <aside
      aria-hidden={!drawerOpen}
      inert={!drawerOpen}
      className={cn(
        "glass-strong absolute bottom-3 right-3 top-3 lg:top-[76px] z-30 flex flex-col overflow-hidden transition-all duration-200",
        wide ? "w-[min(860px,calc(100%-24px))]" : "w-[min(520px,calc(100%-24px))]",
        min && "bottom-auto h-11",
        drawerOpen ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-8 opacity-0",
      )}
    >
      <header className="flex h-11 shrink-0 items-center gap-3 px-3">
        <div className="flex gap-1.5">
          <button className={cn(light, "bg-slate-700")} onClick={toggleDrawer} title="Close" aria-label="Close inspector" />
          <button className={cn(light, "bg-slate-400")} onClick={() => setMin(!min)} title={min ? "Restore" : "Minimize"} aria-label="Minimize inspector" />
          <button className={cn(light, "bg-slate-300")} onClick={() => setWide(!wide)} title={wide ? "Narrow" : "Widen"} aria-label="Widen inspector" />
        </div>
        <div className="flex-1 truncate text-center text-base font-semibold text-slate-900">{STAGES[Math.max(i, 0)].title}</div>
        <div className="flex">
          <button className="grid size-7 place-items-center rounded-full text-slate-600 hover:bg-slate-100 disabled:opacity-30" disabled={i <= 0} onClick={() => select(STAGES[i - 1].id)} aria-label="Previous stage"><ChevronLeft className="size-4" /></button>
          <button className="grid size-7 place-items-center rounded-full text-slate-600 hover:bg-slate-100 disabled:opacity-30" disabled={i >= STAGES.length - 1} onClick={() => select(STAGES[i + 1].id)} aria-label="Next stage"><ChevronRight className="size-4" /></button>
        </div>
      </header>
      {!min && (
        <div className="flex-1 overflow-y-auto p-4">
          <Sheet key={id} />
          <Link href={`/stages/${id}`} className="glass-subtle mt-6 flex items-center justify-between rounded-full px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-200/70">
            {STAGES[Math.max(i, 0)].title} page <ArrowRight className="size-4" />
          </Link>
        </div>
      )}
    </aside>
  );
}

/** The interactive sheet of one stage, for its deep-dive page (server pages pass the id only). */
export function StageSheet({ id }: { id: StageId }) {
  const Sheet = SHEETS[id];
  return <Sheet />;
}
