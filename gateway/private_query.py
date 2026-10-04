"""Runs one read-only SELECT on pg-prod for the local web app's data questions. Private side:
the rows go back to the DBA's browser only, never to the ai service.

Defence in depth: sqlglot must parse exactly one SELECT with no writing node; the session then
runs as the SELECT-only application role (workload.app_role) inside a read-only transaction
with a statement timeout. The query is kept out of pg_stat_statements and auto_explain, so it
never becomes a workload template the ai side sees."""
from __future__ import annotations

import time

import psycopg
import sqlglot
from psycopg import sql as pgsql
from sqlglot import exp

from common.config import cfg

WRITES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
          exp.Command, exp.Into, exp.Lock)


class Rejected(ValueError):
    pass


def check(text: str) -> str:
    """The statement as sqlglot renders it, or Rejected. Only what was checked is run."""
    try:
        stmts = [s for s in sqlglot.parse(text, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise Rejected(f"could not parse the SQL: {str(e)[:200]}") from None
    if len(stmts) != 1:
        raise Rejected(f"expected one statement, got {len(stmts)}")
    s = stmts[0]
    if not isinstance(s, (exp.Select, exp.Union)):
        raise Rejected(f"only SELECT is allowed, got {type(s).__name__}")
    if any(s.find_all(*WRITES)):
        raise Rejected("the statement writes or locks")
    return s.sql(dialect="postgres")


def run(prod_dsn: str, text: str) -> dict:
    query = check(text)
    limit = int(cfg("gateway.private_query_max_rows"))
    t0 = time.monotonic()
    with psycopg.connect(prod_dsn, autocommit=True) as c:
        # superuser settings first, then drop to the SELECT-only role
        c.execute("SET pg_stat_statements.track = 'none'")
        c.execute("SET auto_explain.log_min_duration = -1")
        c.execute(pgsql.SQL("SET ROLE {}").format(pgsql.Identifier(cfg("workload.app_role"))))
        c.execute("SET default_transaction_read_only = on")
        c.execute(pgsql.SQL("SET statement_timeout = {}").format(
            pgsql.Literal(f"{int(cfg('gateway.private_query_timeout_s'))}s")))
        try:
            cur = c.execute(query)
        except psycopg.errors.QueryCanceled:
            raise Rejected("the query ran past gateway.private_query_timeout_s") from None
        except psycopg.Error as e:
            raise Rejected(f"Postgres: {str(e).splitlines()[0][:200]}") from None
        columns = [d.name for d in cur.description or []]
        rows = cur.fetchmany(limit + 1)
    return {"sql": query, "columns": columns, "rows": [list(r) for r in rows[:limit]],
            "truncated": len(rows) > limit, "ms": round((time.monotonic() - t0) * 1000, 1)}
