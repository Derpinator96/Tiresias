"""Measure a configuration on the twin (doc, Component 6). REAL measurement on a
SIMPLIFIED twin. Private side: works on real names; runs in the gateway.

1. Translate each query's equality literals to twin values with the frequency-rank map
   (db/NOTES.md). Range literals pass through: numbers and dates keep their value range.
2. Plan agreement: the twin's operator sequence for each query must match production's
   (EXPLAIN on both) before any twin number is used. A mismatch is reported, not hidden.
3. Before: median of N warm runs (sandbox.timing_runs after sandbox.warmup_runs).
4. Build the configuration's indexes for real on the twin, measure again, record their size
   from pg_relation_size, then drop them so the twin returns to its baseline. before_after()
   does steps 3 and 4 on any connection; db/sandbox/fidelity.py reuses it on pg-prod.
5. Write cost (twin only): pgbench insert latency without and with the indexes
   (db/sandbox/write_cost.py), each run after that phase's read timings so inserted rows never
   touch them.
6. Partition (doc: "Partitioning cannot be hypothesised ... test partitioning on the twin
   only"): a monthly range-partitioned copy of the table (partitioned_copy) is built next to
   it, the configuration's indexes on that table are built on the copy, and the after queries
   are pointed at the copy (retarget). The original table is never renamed, locked for writes
   or changed, so restoring is dropping the copy (in a finally block, and again before a build
   in case a crash left one). Storage delta = the copy's total size minus the original's, plus
   any index on another table. With `writes`, pgbench inserts into the copy for the after phase.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from datetime import date

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
    write_ms_delta: float            # median INSERT ms with the indexes minus without
    after_ops: dict[str, list[str]]  # operator sequence of each after query, with the indexes


def _months(lo: date, hi: date) -> list[date]:
    """First day of every month from lo's month to hi's month, plus the first day after it."""
    out = [date(lo.year, lo.month, 1)]
    while out[-1] <= hi:
        y, m = divmod(out[-1].year * 12 + out[-1].month, 12)   # month index of the next month
        out.append(date(y, m + 1, 1))
    return out


def partitioned_copy(conn, table: str, col: str, name: str) -> None:
    """Build `name`: `table`'s columns, PARTITION BY RANGE (col), one partition per month of
    the data plus a default, rows copied, primary key extended by `col` (Postgres requires the
    partition key in it), the table's own foreign keys (so inserts pay the same reference
    checks), VACUUM ANALYZE. Foreign keys that reference `table` stay on `table`. Drops a
    leftover `name` first."""
    n, t, c = sql.Identifier(name), sql.Identifier(table), sql.Identifier(col)
    conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(n))
    conn.execute(sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) PARTITION BY RANGE ({})").format(n, t, c))
    lo, hi = conn.execute(sql.SQL("SELECT min({c})::date, max({c})::date FROM {t}").format(c=c, t=t)).fetchone()
    bounds = _months(lo, hi) if lo else []
    for a, b in zip(bounds, bounds[1:]):
        conn.execute(sql.SQL("CREATE TABLE {} PARTITION OF {} FOR VALUES FROM ({}) TO ({})").format(
            sql.Identifier(f"{name}_{a:%Y%m}"), n, sql.Literal(a), sql.Literal(b)))
    conn.execute(sql.SQL("CREATE TABLE {} PARTITION OF {} DEFAULT").format(sql.Identifier(f"{name}_default"), n))
    conn.execute(sql.SQL("INSERT INTO {} SELECT * FROM {}").format(n, t))
    # ponytail: copies the primary key only; QuickMart has no other index. Copy every index
    # definition here if the schema ever gets one.
    pk = [r[0] for r in conn.execute("""SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)""", (table,))]
    if pk:
        cols = pk + ([col] if col not in pk else [])
        conn.execute(sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(n, sql.SQL(", ").join(map(sql.Identifier, cols))))
    fks = conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'f'",
                       (table,)).fetchall()
    for (definition,) in fks:          # from the catalog, e.g. FOREIGN KEY (a) REFERENCES t(b)
        conn.execute(sql.SQL("ALTER TABLE {} ADD ").format(n) + sql.SQL(definition))
    conn.execute(sql.SQL("VACUUM ANALYZE {}").format(n))


def retarget(query: str, table: str, new: str) -> str:
    """`query` reading `new` wherever it reads `table`, under the old name as its alias, so
    qualified column references keep working."""
    tree = sqlglot.parse_one(query, dialect="postgres")
    for t in tree.find_all(exp.Table):
        if t.name == table:
            if not t.alias:
                t.set("alias", exp.TableAlias(this=exp.to_identifier(table)))
            t.set("this", exp.to_identifier(new))
    return tree.sql(dialect="postgres")


def total_bytes(conn, table: str) -> int:
    """Heap plus indexes plus TOAST, summed over partitions for a partitioned table
    (pg_partition_tree lists nothing for a plain table or index, hence the fallback)."""
    return int(conn.execute("SELECT COALESCE(sum(pg_total_relation_size(relid)), pg_total_relation_size(%s::regclass)) "
                            "FROM pg_partition_tree(%s::regclass)", (table, table)).fetchone()[0])   # sum() is numeric


def before_after(conn, indexes: list[tuple[str, list[str]]], queries: dict[str, str],
                 after_queries: dict[str, str], prefix: str, writes: bool = False,
                 partition: tuple[str, str] | None = None):
    """On one connection: median ms of each query, then build the indexes for real, record
    their size, each after query's operator sequence and median ms, and drop the indexes
    whatever happens. With `partition` (table, column), the after phase runs on a monthly
    partitioned copy of that table (step 6 above), dropped whatever happens. With `writes`
    (twin only), also the pgbench insert latency without and with the indexes. Returns (before,
    after, storage bytes added, after operator sequences, write ms delta; 0.0 without `writes`
    or without indexes or partition, since writes are then unchanged)."""
    before = {tid: _median_ms(conn, q) for tid, q in queries.items()}
    measure_writes = writes and bool(indexes or partition)
    write_before = write_cost.insert_ms(conn) if measure_writes else 0.0
    copy = f"{prefix}part"
    if partition:
        after_queries = {tid: retarget(q, partition[0], copy) for tid, q in after_queries.items()}
        indexes = [(copy if t == partition[0] else t, cols) for t, cols in indexes]
    names = [f"{prefix}{i}" for i in range(len(indexes))]
    try:
        if partition:
            partitioned_copy(conn, partition[0], partition[1], copy)
        for name, (table, cols) in zip(names, indexes):
            conn.execute(sql.SQL("CREATE INDEX {} ON {} ({})").format(
                sql.Identifier(name), sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols))))
        if partition:
            size = total_bytes(conn, copy) - total_bytes(conn, partition[0]) + sum(
                total_bytes(conn, n) for n, (t, _) in zip(names, indexes) if t != copy)
        else:
            size = sum(conn.execute("SELECT pg_relation_size(%s::regclass)", (n,)).fetchone()[0] for n in names)
        ops = {tid: op_sequence(_explain(conn, q)) for tid, q in after_queries.items()}
        after = {tid: _median_ms(conn, q) for tid, q in after_queries.items()}
        write_table = copy if partition and partition[0] == "sales" else "sales"
        write_after = write_cost.insert_ms(conn, write_table) if measure_writes else 0.0
    finally:
        for name in names:
            conn.execute(sql.SQL("DROP INDEX IF EXISTS {}").format(sql.Identifier(name)))
        if partition:
            conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(copy)))
    return before, after, size, ops, write_after - write_before


def measure(prod_dsn: str, twin_dsn: str, indexes: list[tuple[str, list[str]]],
            queries: dict[str, str], after_queries: dict[str, str] | None = None,
            partition: tuple[str, str] | None = None) -> TwinResult:
    """before = `queries` without the indexes; after = `after_queries` (rewritten SQL, where a
    template has a rewrite; otherwise the same query) with the indexes and, with `partition`,
    on a monthly partitioned copy of that table."""
    mapping = load_map()
    twin_q = {tid: map_query(q, mapping) for tid, q in queries.items()}
    twin_after = {tid: map_query((after_queries or {}).get(tid, q), mapping) for tid, q in queries.items()}
    with psycopg.connect(prod_dsn, autocommit=True) as prod:
        prod_ops = {tid: op_sequence(_explain(prod, q)) for tid, q in queries.items()}
    with psycopg.connect(twin_dsn, autocommit=True) as conn:
        agree = {tid: op_sequence(_explain(conn, q)) == prod_ops[tid] for tid, q in twin_q.items()}
        before, after, size, ops, write_delta = before_after(conn, indexes, twin_q, twin_after, "bt_sim_", writes=True,
                                                         partition=partition)
    return TwinResult(before, after, size / 2**20, int(cfg("sandbox.timing_runs")), agree, twin_q, write_delta, ops)
