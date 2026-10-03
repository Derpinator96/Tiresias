"""Column and table metadata. From pg_stats only n_distinct, null_frac and
most_common_freqs are read; most_common_vals and histogram_bounds hold real values and are
never even selected. Skew = sum of the top K most-common-value frequencies (K from config)."""
from __future__ import annotations

import psycopg

from common.config import cfg
from gateway.catalog import Catalog
from gateway.hashing import Hasher
from gateway.rounding import round_count, round_sig

DATE_TYPES = {"date", "timestamp without time zone", "timestamp with time zone"}
NUMBER_TYPES = {"integer", "bigint", "smallint", "numeric", "real", "double precision"}


def type_class(cat: Catalog, table: str, col: str) -> str:
    typ = cat.columns[table][col]
    if (table, col) in cat.pk or (table, col) in cat.fk:
        return "id"
    if typ in DATE_TYPES:
        return "date"
    if typ in NUMBER_TYPES:
        return "number"
    return "text"


def column_meta(conn: psycopg.Connection, cat: Catalog, hasher: Hasher, roles: set[tuple[str, str]]) -> list[dict]:
    """roles: (column code, role) pairs seen in the workload's templates."""
    k = int(cfg("gateway.skew_top_mcv_count"))
    reltuples = dict(conn.execute("""SELECT relname, reltuples FROM pg_class
                                     WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'""").fetchall())
    stats = {(t, c): (nd, nf, freqs) for t, c, nd, nf, freqs in conn.execute("""
        SELECT tablename, attname, n_distinct, null_frac, most_common_freqs
        FROM pg_stats WHERE schemaname = 'public'""")}
    out = []
    for table, cols in cat.columns.items():
        for col in cols:
            code = hasher.column(table, col)
            nd, nf, freqs = stats.get((table, col), (0, 0.0, None))
            distinct = -nd * max(reltuples.get(table, 0), 0) if nd < 0 else nd
            out.append({
                "table": hasher.table(table),
                "col": code,
                "type_class": type_class(cat, table, col),
                "bits": {
                    "pk": (table, col) in cat.pk, "fk": (table, col) in cat.fk,
                    "indexed": (table, col) in cat.indexed, "nullable": (table, col) in cat.nullable,
                    "join": (code, "JOIN") in roles, "range": (code, "RANGE") in roles, "eq": (code, "EQ") in roles,
                },
                "n_distinct": round_count(distinct),
                "null_frac": round(float(nf), 4),
                "skew": round(min(1.0, float(sum(sorted(freqs or [], reverse=True)[:k]))), 4),
            })
    return out


def table_meta(conn: psycopg.Connection, cat: Catalog, hasher: Hasher) -> list[dict]:
    rows = conn.execute("""
        SELECT c.relname, c.reltuples, pg_total_relation_size(c.oid),
               COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0),
               EXTRACT(EPOCH FROM now() - COALESCE(d.stats_reset, pg_postmaster_start_time()))
        FROM pg_class c
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        CROSS JOIN pg_stat_database d
        WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' AND d.datname = current_database()
    """).fetchall()
    out = []
    for name, reltuples, size_bytes, writes, seconds in rows:
        if name not in cat.columns:
            continue
        out.append({
            "table": hasher.table(name),
            "rows": round_count(max(reltuples, 0)),
            "size_mb": round_sig(size_bytes / 2**20),
            # Measured: row writes since the stats reset, per second. The seed's bulk COPY
            # counts as writes; there is no steady write workload yet (pgbench is pending).
            "writes_per_s": round_sig(float(writes) / float(seconds)) if seconds else 0.0,
        })
    return out
