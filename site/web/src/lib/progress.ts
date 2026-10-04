// Which pipeline stage a live question is in, from the ai service's progress events ("tool
// <name> -> <id>", agent/agent.py) and the job state. Pure, no imports, so Node tests load it.

export type StageId = "source" | "gateway" | "miner" | "gnn" | "rl" | "llm" | "twin" | "dba";
export const ORDER: StageId[] = ["source", "gateway", "miner", "gnn", "rl", "llm", "twin", "dba"];

const TOOL_STAGE: Record<string, StageId> = {
  get_slow_templates: "gateway",
  get_plan: "gnn",
  gnn_explain: "gnn",
  mine_candidates: "miner",
  run_rl: "rl",
  rewrite_candidates: "twin",
  verify: "twin",
  simulate: "twin",
};

/** The tool name in one event, or null for retry and failover lines. */
export const toolOf = (event: string) => /^tool (\w+) ->/.exec(event)?.[1] ?? null;

/** Current stage: source once the question is received, then the stage of the latest tool call,
 *  llm once the answer is back, dba once the SQL is written (done). */
export function stageOf(events: string[], answered: boolean, done: boolean): StageId {
  if (done) return "dba";
  if (answered) return "llm";
  for (let i = events.length - 1; i >= 0; i--) {
    const t = toolOf(events[i]);
    if (t && TOOL_STAGE[t]) return TOOL_STAGE[t];
  }
  return "source";
}

/** Every stage reached so far, in pipeline order, for "done" ticks on the diagram. */
export function reached(events: string[], answered: boolean, done: boolean): Set<StageId> {
  const s = new Set<StageId>(["source"]);
  for (const e of events) { const t = toolOf(e); if (t && TOOL_STAGE[t]) s.add(TOOL_STAGE[t]); }
  if (events.some((e) => toolOf(e))) s.add("gateway"); // every tool call goes through the gateway
  if (answered) s.add("llm");
  if (done) ORDER.forEach((x) => s.add(x));
  return s;
}
