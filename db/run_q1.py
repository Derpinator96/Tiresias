"""Run Q1, Q2, the two-region query (and Q3 if workload.q3_in_seed) on pg-prod so they appear in
pg_stat_statements and, when slower than workload.slow_query_ms, in the auto_explain log.
Also runs the four canary queries once.

    python -m db.run_q1        # prints each Q1 duration in ms
"""
from __future__ import annotations

import os
import statistics
import time

import psycopg

from common.config import cfg
from db import workload


def app_dsn(admin_dsn: str) -> str:
    """Same server and password, connecting as the application role from config.yaml."""
    return psycopg.conninfo.make_conninfo(admin_dsn, user=cfg("workload.app_role"))


def run(dsn: str, runs: int | None = None) -> list[float]:
    runs = int(cfg("workload.q1_runs")) if runs is None else runs
    durations = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for sql in workload.canary_queries():
            conn.execute(sql).fetchall()
        for _ in range(runs):
            t0 = time.perf_counter()
            conn.execute(workload.q1_sql()).fetchall()
            durations.append((time.perf_counter() - t0) * 1000)
        for _ in range(int(cfg("workload.q2_runs"))):
            conn.execute(workload.q2_sql()).fetchall()
            conn.execute(workload.qor_sql()).fetchall()
        for _ in range(int(cfg("workload.q3_runs")) if cfg("workload.q3_in_seed") else 0):
            conn.execute(workload.q3_sql()).fetchall()
    return durations


if __name__ == "__main__":
    ms = run(app_dsn(os.environ["PROD_DSN"]))
    print("Q1 durations (ms):", ", ".join(f"{x:.1f}" for x in ms))
    print(f"Q1 median: {statistics.median(ms):.1f} ms over {len(ms)} runs")
