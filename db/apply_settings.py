"""Apply tunable Postgres settings from config.yaml to pg-prod with ALTER SYSTEM.

Static settings (preload libraries, log destination) live in infra/postgres/postgresql.conf.
The values here are tunables, so they come from config.yaml, never from a .conf file.
"""
from __future__ import annotations

import psycopg

from common.config import cfg


def settings() -> dict[str, str]:
    return {
        "pg_stat_statements.track": str(cfg("postgres.pg_stat_statements_track")),
        # Decision A: auto_explain's threshold is workload.slow_query_ms.
        "auto_explain.log_min_duration": f"{int(cfg('workload.slow_query_ms'))}ms",
        "auto_explain.log_analyze": "on" if cfg("postgres.auto_explain_log_analyze") else "off",
    }


def apply(dsn: str) -> dict[str, str]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name, value in settings().items():
            # ALTER SYSTEM does not take bind parameters; values come from config.yaml only.
            conn.execute(f"ALTER SYSTEM SET {name} = '{value}'")
        conn.execute("SELECT pg_reload_conf()")
        # Settings reload asynchronously; read them back on a fresh connection.
    with psycopg.connect(dsn, autocommit=True) as conn:
        return {n: conn.execute(f"SHOW {n}").fetchone()[0] for n in settings()}
