"""Result checksums on the twin (doc, Detailed component specs, Verification): an MD5 of the
sorted result rows. Private side: runs real SQL on pg-twin from the gateway.

For the walking skeleton this proves one thing: building the recommended indexes does not
change a template's answer. Rewrite equivalence (original vs rewritten SQL) plugs in here
when rewrites exist.
"""
from __future__ import annotations

import psycopg
from psycopg import sql


def result_md5(conn: psycopg.Connection, query: str) -> tuple[str, int]:
    """(MD5 of the sorted rows, row count). Rows are rendered as text and sorted, so the
    checksum does not depend on the order the plan returns them in."""
    md5, n = conn.execute(
        f"SELECT md5(COALESCE(string_agg(r::text, E'\\n' ORDER BY r::text), '')), COUNT(*) FROM ({query}) AS r"
    ).fetchone()
    return md5, n


def index_preserves_results(twin_dsn: str, indexes: list[tuple[str, list[str]]], query: str) -> dict:
    with psycopg.connect(twin_dsn, autocommit=True) as conn:
        before, n_before = result_md5(conn, query)
        names = [f"bt_chk_{i}" for i in range(len(indexes))]
        try:
            for name, (table, cols) in zip(names, indexes):
                conn.execute(sql.SQL("CREATE INDEX {} ON {} ({})").format(
                    sql.Identifier(name), sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols))))
            after, n_after = result_md5(conn, query)
        finally:
            for name in names:
                conn.execute(sql.SQL("DROP INDEX IF EXISTS {}").format(sql.Identifier(name)))
    return {"match": before == after and n_before == n_after, "rows": n_after}
