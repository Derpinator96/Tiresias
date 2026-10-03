// Plan GNN visual logic, mirroring models/gnn/features.py (FEATURE_VERSION 1). No imports, so
// tests/gnn.test.mjs loads it with Node's type stripping.

export type PlanNode = {
  node_id: number; parent_id: number | null; op: string; est_rows: number; est_cost: number; width: number;
  filter_cols?: string[]; filter_redacted?: boolean; index?: string; relation?: string; actual_rows?: number; self_ms?: number;
};

/** Own cost per node: est_cost minus the est_cost of its children (floored at 0). */
export function ownCost(nodes: PlanNode[]): number[] {
  return nodes.map((n) => Math.max(0, n.est_cost - nodes.filter((c) => c.parent_id === n.node_id).reduce((a, c) => a + c.est_cost, 0)));
}

/** The 7 numeric features of features.py node_features, in order. */
export function numericFeatures(nodes: PlanNode[]): number[][] {
  const own = ownCost(nodes);
  return nodes.map((n, i) => [Math.log1p(n.est_rows), Math.log1p(n.est_cost), Math.log1p(own[i]), Math.log1p(n.width), n.index ? 1 : 0, n.filter_cols?.length ?? 0, n.filter_redacted ? 1 : 0]);
}

/** One-hot index of the operator, or -1 when unknown. */
export const opIndex = (ops: string[], op: string) => ops.indexOf(op);

/** Share of the plan's total for each node: Postgres's own cost, or measured self_ms. */
export function shares(nodes: PlanNode[], by: "cost" | "time"): number[] {
  const v = by === "cost" ? ownCost(nodes) : nodes.map((n) => n.self_ms ?? 0);
  const t = v.reduce((a, b) => a + b, 0) || 1;
  return v.map((x) => x / t);
}

/** Nodes whose information reaches `target` after `layers` message-passing layers: a layer
 *  attends over a node and its children, so information climbs one level per layer. */
export function reach(nodes: PlanNode[], target: number, layers: number): Set<number> {
  const seen = new Set<number>([target]);
  let frontier = [target];
  for (let l = 0; l < layers; l++) {
    frontier = frontier.flatMap((id) => nodes.filter((n) => n.parent_id === id).map((n) => n.node_id)).filter((id) => !seen.has(id));
    frontier.forEach((id) => seen.add(id));
  }
  return seen;
}

export type Placed = { id: number; x: number; y: number };

/** Tidy tree layout: y is the depth (root 0), x is in leaf units (leaves 0, 1, 2 ... left to right,
 *  a parent centred over its children). Two nodes in different subtrees are at least 1 unit apart,
 *  so boxes up to one unit wide never overlap at any depth. */
export function layout(nodes: PlanNode[]): Placed[] {
  const kids = (id: number) => nodes.filter((n) => n.parent_id === id).map((n) => n.node_id);
  const depth = new Map<number, number>();
  const xs = new Map<number, number>();
  let leaf = 0;
  const walk = (id: number, d: number): number => {
    depth.set(id, d);
    const k = kids(id);
    const x = k.length ? k.map((c) => walk(c, d + 1)).reduce((a, b) => a + b, 0) / k.length : leaf++;
    xs.set(id, x);
    return x;
  };
  walk(nodes.find((n) => n.parent_id === null)!.node_id, 0);
  return nodes.map((n) => ({ id: n.node_id, x: xs.get(n.node_id)!, y: depth.get(n.node_id)! }));
}

/** The serving rule (models/gnn load_predictor): the GNN serves only when its scored median
 *  q-error is below the Postgres baseline's. */
export const serves = (gnnMedian: number, baselineMedian: number) => (gnnMedian < baselineMedian ? "gnn" : "baseline");

/** How many times the estimate was off the actual rows (always >= 1), for the ANALYZE alert. */
export const misestimate = (est: number, actual: number) => Math.max(est, actual) / Math.max(1, Math.min(est, actual));

// Bundle helpers (src/lib/bundle.ts shapes, structural so this file stays import free).
type BundleLike = { template_ids: string[]; plans: Record<string, { nodes: PlanNode[] }[]>; names: Record<string, string> };

/** First line of a SQL text, at most `max` characters, for a picker label. */
export function shortSql(sql: string, max = 60): string {
  const s = sql.replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max - 3).trimEnd()}...` : s;
}

/** The bundle's templates that have a logged plan: the asked question's templates first, then
 *  every other template in the bundle, labelled with the real SQL. */
export function planOptions(b: BundleLike): { tid: string; label: string }[] {
  const ids = [...b.template_ids, ...Object.keys(b.plans).filter((t) => !b.template_ids.includes(t))];
  return ids.filter((t) => b.plans[t]?.length).map((tid) => ({ tid, label: shortSql(b.names[tid] ?? tid) }));
}

/** A prediction's per-node shares in plan node order (0 for a node the prediction does not name). */
export function predictedShares(nodes: PlanNode[], pred: { nodes: { node_id: number; share: number }[] } | null | undefined): number[] {
  const by = new Map((pred?.nodes ?? []).map((n) => [n.node_id, n.share]));
  return nodes.map((n) => by.get(n.node_id) ?? 0);
}
