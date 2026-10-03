"""make seed: load QuickMart into pg-prod, apply settings, reset stats, run the workload.

    python -m db.seed
"""
from __future__ import annotations

import os
import statistics

import psycopg
from psycopg import sql

from common.config import cfg
from db import apply_settings, generate, run_q1


def main() -> None:
    dsn = os.environ["PROD_DSN"]
    print("sizes:", generate.sizes())
    timings = generate.load(dsn)
    print("load timings (s):", {k: round(v, 1) for k, v in timings.items()})
    print("settings:", apply_settings.apply(dsn))
    role = cfg("workload.app_role")
    with psycopg.connect(dsn, autocommit=True) as conn:
        # The application role shares the admin password: one secret in .env, private network only.
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        password = psycopg.conninfo.conninfo_to_dict(dsn)["password"]
        verb = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
        conn.execute("SELECT pg_stat_statements_reset()")
    ms = run_q1.run(run_q1.app_dsn(dsn))
    print("Q1 durations (ms):", ", ".join(f"{x:.1f}" for x in ms))
    print(f"Q1 median: {statistics.median(ms):.1f} ms over {len(ms)} runs")


if __name__ == "__main__":
    main()
