"""Measure a configuration on the twin (doc, Component 6). REAL measurement on a
SIMPLIFIED twin. Private side: works on real names; runs in the gateway.

1. Translate each query's equality literals to twin values with the frequency-rank map
   (db/NOTES.md). Range literals pass through: numbers and dates keep their value range.
2. Plan agreement: the twin's operator sequence for each query must match production's
   (EXPLAIN on both) before any twin number is used. A mismatch is reported, not hidden.
3. Before: median of N warm runs (sandbox.timing_runs after sandbox.warmup_runs).
4. Build the configuration's indexes for real on the twin, measure again, record their size
   from pg_relation_size, then drop them so the twin returns to its baseline.
5. Write cost: pgbench insert latency without and with the indexes (db/sandbox/write_cost.py),
   each run after that phase's read timings so inserted rows never touch them.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass

import psycopg
import sqlglot
from psycopg import sql
from sqlglot import exp

from common.config import cfg
from db.sandbox import write_cost


def load_map() -> dict[str, dict[str, object]]:
    with open(cfg("sandbox.twin_map_path"), encoding="utf-8") as f:
        raw = json.load(f)
    return {col: {str(real): twin for real, twin in pairs} for col, pairs in raw.items()}


def map_query(query: str, mapping: dict[str, dict[str, object]]) -> str:
    """Replace `column = literal` and `column IN (...)` literals that have a twin value."""
    tree = sqlglot.parse_one(query, dialect="postgres")
    aliases = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    tables = sorted(set(aliases.values()))

    def table_of(col: exp.Column) -> str | None:
        if col.table:
            return aliases.get(col.table)
        owners = [t for t in tables if f"{t}.{col.name}" in mapping]
        return owners[0] if len(owners) == 1 else None

    def twin_literal(col: exp.Column, lit: exp.Literal) -> exp.Expression:
        t = table_of(col)
        m = mapping.get(f"{t}.{col.name}") if t else None
        if not m or lit.this not in m:
            return lit
        v = m[lit.this]
        return exp.Literal.number(v) if isinstance(v, (int, float)) else exp.Literal.string(str(v))

    for node in list(tree.find_all(exp.EQ)):
        if isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Literal):
            node.expression.replace(twin_literal(node.this, node.expression))
    for node in list(tree.find_all(exp.In)):
        if isinstance(node.this, exp.Column):
            for lit in [e for e in node.expressions if isinstance(e, exp.Literal)]:
                lit.replace(twin_literal(node.this, lit))
    return tree.sql(dialect="postgres")


def op_sequence(plan_json: dict) -> list[str]:
    out = []

    def walk(n):
        out.append(n["Node Type"])
        for c in n.get("Plans", []):
            walk(c)
    walk(plan_json["Plan"])
    return out


def _explain(conn, query: str) -> dict:
    return conn.execute(f"EXPLAIN (FORMAT JSON) {query}").fetchone()[0][0]


def _median_ms(conn, query: str) -> float:
    for _ in range(int(cfg("sandbox.warmup_runs"))):
        conn.execute(query).fetchall()
    times = []
    for _ in range(int(cfg("sandbox.timing_runs"))):
        t0 = time.perf_counter()
        conn.execute(query).fetchall()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


@dataclass
class TwinResult:
    before_ms: dict[str, float]
    after_ms: dict[str, float]
    storage_mb: float
    runs: int
    plan_agreement: dict[str, bool]
    twin_queries: dict[str, str]     # private: twin literals, never sent
    write_ms_delta: float            # average INSERT ms with the indexes minus without


def measure(prod_dsn: str, twin_dsn: str, indexes: list[tuple[str, list[str]]],
            queries: dict[str, str], after_queries: dict[str, str] | None = None) -> TwinResult:
    """before = `queries` without the indexes; after = `after_queries` (rewritten SQL, where a
    template has a rewrite; otherwise the same query) with the indexes."""
    mapping = load_map()
    twin_q = {tid: map_query(q, mapping) for tid, q in queries.items()}
    twin_after = {tid: map_query((after_queries or {}).get(tid, q), mapping) for tid, q in queries.items()}
    with psycopg.connect(prod_dsn, autocommit=True) as prod:
        prod_ops = {tid: op_sequence(_explain(prod, q)) for tid, q in queries.items()}
    with psycopg.connect(twin_dsn, autocommit=True) as conn:
        agree = {tid: op_sequence(_explain(conn, q)) == prod_ops[tid] for tid, q in twin_q.items()}
        before = {tid: _median_ms(conn, q) for tid, q in twin_q.items()}
        write_before = write_cost.insert_ms(conn) if indexes else 0.0   # no index: writes unchanged
        names = [f"bt_sim_{i}" for i in range(len(indexes))]
        try:
            for name, (table, cols) in zip(names, indexes):
                conn.execute(sql.SQL("CREATE INDEX {} ON {} ({})").format(
                    sql.Identifier(name), sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols))))
            size = sum(conn.execute("SELECT pg_relation_size(%s::regclass)", (n,)).fetchone()[0] for n in names)
            after = {tid: _median_ms(conn, q) for tid, q in twin_after.items()}
            write_after = write_cost.insert_ms(conn) if indexes else 0.0
        finally:
            for name in names:
                conn.execute(sql.SQL("DROP INDEX IF EXISTS {}").format(sql.Identifier(name)))
    return TwinResult(before, after, size / 2**20, int(cfg("sandbox.timing_runs")), agree, twin_q,
                      write_after - write_before)
