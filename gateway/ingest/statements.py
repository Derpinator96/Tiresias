"""Slow query templates from pg_stat_statements, hashed into HashedQuery objects.

Only the application role's queries are read (config workload.app_role), so test and
catalog queries never become templates. Values are already $n there; the gateway still
parses and strips every statement, and withholds any it cannot parse (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from common.config import cfg
from gateway.hashing import Hasher
from gateway.rounding import round_count
from gateway.strip import Unparsed, hash_sql


@dataclass
class Template:
    """Private record of one template. Only `hashed` ever leaves the gateway."""
    template_id: str
    normalized_sql: str            # real names, $n placeholders
    queryids: list[int]
    hashed: dict                   # HashedQuery
    calls: int = 0                 # raw, unrounded: drift windows difference these privately
    total_ms: float = 0.0


def read(conn: psycopg.Connection, hasher: Hasher, schema: dict[str, set[str]]) -> tuple[list[Template], int]:
    """All parseable templates of the app role, ranked by total time, plus the count withheld."""
    rows = conn.execute("""
        SELECT s.queryid, s.query, s.calls, s.total_exec_time
        FROM pg_stat_statements s
        JOIN pg_roles r ON r.oid = s.userid
        JOIN pg_database d ON d.oid = s.dbid
        WHERE r.rolname = %s AND d.datname = current_database() AND s.toplevel""",
        (cfg("workload.app_role"),)).fetchall()
    by_id: dict[str, Template] = {}
    totals: dict[str, list[float]] = {}
    withheld = 0
    for queryid, query, calls, total_ms in rows:
        try:
            sql, columns = hash_sql(query, hasher, schema)
        except Unparsed:
            withheld += 1          # "unparsed, not sent": the text never leaves
            continue
        tid = hasher.template(query)
        if tid in by_id:
            by_id[tid].queryids.append(queryid)
        else:
            by_id[tid] = Template(tid, query, [queryid], {"template_id": tid, "sql": sql, "columns": columns})
        acc = totals.setdefault(tid, [0, 0.0])
        acc[0] += calls
        acc[1] += total_ms
    out = []
    for tid, t in by_id.items():
        calls, total_ms = totals[tid]
        t.calls, t.total_ms = calls, total_ms
        t.hashed.update({
            "calls": round_count(calls),
            "mean_ms": round(total_ms / calls, 1) if calls else 0.0,
            "total_ms": round(total_ms, 1),
        })
        t.hashed = {k: t.hashed[k] for k in ("template_id", "sql", "calls", "mean_ms", "total_ms", "columns")}
        out.append(t)
    out.sort(key=lambda t: t.hashed["total_ms"], reverse=True)
    return out, withheld
