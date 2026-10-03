"""Pattern miner (doc, Component 2 and Detailed component specs). REAL.

1. One basket per template: items are `column:ROLE` (EQ, JOIN, RANGE, GROUP, ORDER; SELECT
   is not an index signal and is left out), weighted by the template's total time.
2. mlxtend's FP-Growth takes no weights, so it runs unweighted at a low threshold, then each
   found itemset's support is recomputed as its share of total time and filtered.
3. Each frequent itemset on one table becomes a candidate index: `=` columns first (EQ, then
   JOIN), then range columns, then ORDER BY columns; at most N columns; the leading column
   must have at least M distinct values.
4. Candidates already covered by an existing index are dropped; the top K are kept.

Checked against mlxtend 0.25.0: fpgrowth(df, min_support, null_values, use_colnames,
max_len, verbose) returns columns `support` and `itemsets` (frozensets).
"""
from __future__ import annotations

import hashlib

import pandas as pd
from mlxtend.frequent_patterns import fpgrowth

from common.config import cfg

INDEX_ROLES = ("EQ", "JOIN", "RANGE", "ORDER", "GROUP")
# Index column order by role; GROUP items never enter a candidate.
ROLE_ORDER = {role: rank for rank, role in enumerate(["EQ", "JOIN", "RANGE", "ORDER"])}


def baskets(templates: list[dict]) -> tuple[list[set[str]], list[float], dict[str, str], list[str]]:
    """(item sets, weights, column -> table, template IDs) from HashedQuery objects."""
    items, weights, col_table, tids = [], [], {}, []
    for t in templates:
        basket = set()
        for c in t["columns"]:
            col_table[c["col"]] = c["table"]
            if c["role"] in INDEX_ROLES:
                basket.add(f"{c['col']}:{c['role']}")
        if basket:
            items.append(basket)
            weights.append(float(t["total_ms"]))
            tids.append(t["template_id"])
    return items, weights, col_table, tids


def frequent_itemsets(items: list[set[str]], weights: list[float]) -> list[tuple[frozenset, float]]:
    """FP-Growth unweighted at a low threshold, then support recomputed by time weight."""
    if not items:
        return []
    vocab = sorted(set().union(*items))
    df = pd.DataFrame([[i in b for i in vocab] for b in items], columns=vocab)
    found = fpgrowth(df, min_support=float(cfg("miner.unweighted_min_support")), use_colnames=True,
                     max_len=int(cfg("miner.max_index_columns")))
    total = sum(weights) or 1.0
    min_w = float(cfg("miner.min_weighted_support"))
    out = []
    for itemset in found["itemsets"]:
        w = sum(wt for b, wt in zip(items, weights) if itemset <= b) / total
        if w >= min_w:
            out.append((frozenset(itemset), w))
    return out


def _covered(table: str, cols: list[str], existing: list[tuple[str, list[str]]]) -> bool:
    """An index on (a, b) covers (a) and (a, b): a candidate is covered by any existing index
    on the same table whose leading columns equal it."""
    return any(t == table and idx[: len(cols)] == cols for t, idx in existing)


def candidates(templates: list[dict], column_meta: list[dict],
               existing_indexes: list[tuple[str, list[str]]] | None = None) -> list[dict]:
    """Candidate objects (contract Candidate), best first."""
    items, weights, col_table, tids = baskets(templates)
    distinct = {c["col"]: c["n_distinct"] for c in column_meta}
    max_cols = int(cfg("miner.max_index_columns"))
    min_lead = int(cfg("miner.min_leading_distinct"))
    existing = existing_indexes or []
    best: dict[tuple, dict] = {}
    for itemset, support in frequent_itemsets(items, weights):
        parsed = [tuple(i.split(":")) for i in itemset]
        tables = {col_table[c] for c, _ in parsed}
        if len(tables) != 1:
            continue                                   # an index lives on one table
        table = tables.pop()
        ordered = sorted((p for p in parsed if p[1] in ROLE_ORDER),
                         key=lambda p: (ROLE_ORDER[p[1]], -distinct.get(p[0], 0), p[0]))
        cols: list[str] = []
        for c, _ in ordered:
            if c not in cols:
                cols.append(c)
        cols = cols[:max_cols]
        if not cols or distinct.get(cols[0], 0) < min_lead or _covered(table, cols, existing):
            continue
        key = (table, tuple(cols))
        if key in best and best[key]["support"] >= support:
            continue
        best[key] = {
            "cand_id": "cand_" + hashlib.sha256(f"{table}:{','.join(cols)}".encode()).hexdigest()[:8],
            "table": table,
            "columns": cols,
            "support": round(support, 4),
            "evidence": {"items": sorted(itemset),
                         "templates": [t for t, b in zip(tids, items) if itemset <= b]},
        }
    ranked = sorted(best.values(), key=lambda c: (-c["support"], -len(c["columns"]), c["cand_id"]))
    return ranked[: int(cfg("miner.candidates_kept"))]
