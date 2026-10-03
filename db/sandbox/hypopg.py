"""HypoPG what-if (doc, Component 6). REAL. Private side: works on real names, runs in the
gateway, never in ai.

Hypothetical indexes live only in the session that made them, so creating them and every
EXPLAIN happen on one connection, and the session is reset before and after.

Checked against HypoPG 1.4.3 on PostgreSQL 16.15: hypopg_create_index(sql) returns
(indexrelid, indexname); hypopg_relation_size(oid) returns bytes; hypopg_reset() clears.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import sql


@dataclass
class WhatIf:
    plans: dict[str, dict]          # template_id -> EXPLAIN (FORMAT JSON) plan, real names
    index_bytes: int                # estimated size of every hypothetical index created


def explain_with_indexes(dsn: str, indexes: list[tuple[str, list[str]]],
                         queries: dict[str, tuple[str, bool]]) -> WhatIf:
    """indexes: [(table, [columns in order])]. queries: template_id -> (sql, is_generic).
    A generic query keeps its $n placeholders and is planned with EXPLAIN (GENERIC_PLAN),
    new in PostgreSQL 16."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT hypopg_reset()")
        try:
            size = 0
            for table, cols in indexes:
                ddl = sql.SQL("CREATE INDEX ON {} ({})").format(
                    sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in cols)).as_string(conn)
                oid, _name = conn.execute("SELECT * FROM hypopg_create_index(%s)", (ddl,)).fetchone()
                size += conn.execute("SELECT hypopg_relation_size(%s)", (oid,)).fetchone()[0]
            plans = {}
            for tid, (query, generic) in queries.items():
                opts = "GENERIC_PLAN, FORMAT JSON" if generic else "FORMAT JSON"
                plans[tid] = conn.execute(f"EXPLAIN ({opts}) {query}").fetchone()[0][0]
            return WhatIf(plans, int(size))
        finally:
            conn.execute("SELECT hypopg_reset()")
