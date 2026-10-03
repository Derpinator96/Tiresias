// Every figure below is from a measured run (see CLAUDE.md "Current state" and the NOTES.md files).
// Q1: e2e run_d1b30d38. Q2 and fidelity: make fidelity on the correlated twin. Q4: make drift-demo.
// GNN: reference model, data/gnn/ref_results_full.json (final trainer weights pending).

export const facts = [
  ["67.6%", "Q1 faster on the twin"],
  ["0", "canary leaks in 43 payloads"],
  ["10M", "rows in the demo database"],
  ["16,420", "plans used to train the GNN"],
];

export const sql = {
  dba: {
    label: "DBA view",
    text: "SELECT SUM(amount)\nFROM sales\nWHERE region_id = 7\n  AND transaction_date >= '2026-09-26';",
    note: "Real names and values. Stays on the private side.",
  },
  ai: {
    label: "AI view",
    text: "SELECT SUM(c_4e1a90d2)\nFROM t_9b37c0e5\nWHERE c_17f2ab48 = ?\n  AND c_d03c6e91 >= ?;",
    note: "HMAC codes, values removed. All the model receives. Codes shown are illustrative.",
  },
};

export const privateSide = [
  ["Production Postgres", "pg_stat_statements, auto_explain"],
  ["Statistical twin", "synthetic rows from pg_stats, correlated pairs"],
  ["HypoPG", "hypothetical indexes"],
  ["VeriEQL", "bounded SQL equivalence"],
  ["Approve", "migration, rollback, post-deploy check"],
];

export const aiSide = [
  ["FP-Growth miner", "index candidates, workload drift"],
  ["Plan GNN", "runtime and bottleneck prediction"],
  ["Q-learning search", "indexes and rewrites, top 3 re-measured"],
  ["LLM agent", "8 tools, every number cited"],
  ["Egress", "LLM host only, or fully air-gapped"],
];

export const pipeline = [
  ["Capture", "Slow query templates and plans from Postgres statistics."],
  ["Hash", "Names become keyed codes, literals are removed, every payload is scanned and logged."],
  ["Mine", "FP-Growth finds the columns that slow queries filter on together."],
  ["Search", "Q-learning over indexes and rewrites, costed by HypoPG and the GNN."],
  ["Measure", "The top three configurations are built on the twin. The best measured wins."],
  ["Approve", "Migration and rollback scripts, with an automatic regression check."],
];

export const results = [
  ["Q1 weekly sales", "Index (region_id, transaction_date)", "303.6", "98.3", "67.6%", "Checksum match"],
  ["Q2 monthly category", "Rewrite + index (store_id, transaction_date)", "1,327.2", "735.8", "44.6%", "Tested"],
  ["Q4 after drift", "Index (transaction_date)", "252.0", "120.4", "52.2%", "Plans agree"],
  ["Two-region report", "OR to IN rewrite", "", "", "", "Verified"],
];

export const measurements = [
  ["Twin fidelity, Q1 / Q2 / two-region", "0.76 / 0.99 / 0.95"],
  ["Region-7 share of sales, production / twin", "30.01% / 30.00%"],
  ["Insert latency added by the Q1 index", "+0.03 ms"],
  ["Drift distance after the switch to Q4 (threshold 0.20)", "0.43, 0.48"],
];

export const gnn = {
  headline: "42%",
  median: [["PostgreSQL", 3.27], ["Gradient boosting", 1.79], ["Plan GNN", 1.89]],
  p95: [["PostgreSQL", 25.6], ["Gradient boosting", 11.79], ["Plan GNN", 9.64]],
};

export const proofs = [
  ["Canary scan", "0 hits", "Planted secrets never appear in an outbound payload."],
  ["Negative control", "Leaks caught", "With hashing off, the same scanner finds the canaries."],
  ["Network isolation", "No route", "The AI container cannot reach either database."],
  ["Air-gapped mode", "Local model", "A local LLM through Ollama. Nothing leaves the machine."],
];
