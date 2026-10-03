"""make seed: load QuickMart into pg-prod, apply settings, reset stats, run the workload.

    python -m db.seed
"""
from __future__ import annotations

import os
import statistics

import psycopg

from db import apply_settings, generate, run_q1


def main() -> None:
    dsn = os.environ["PROD_DSN"]
    print("sizes:", generate.sizes())
    timings = generate.load(dsn)
    print("load timings (s):", {k: round(v, 1) for k, v in timings.items()})
    print("settings:", apply_settings.apply(dsn))
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_stat_statements_reset()")
    ms = run_q1.run(dsn)
    print("Q1 durations (ms):", ", ".join(f"{x:.1f}" for x in ms))
    print(f"Q1 median: {statistics.median(ms):.1f} ms over {len(ms)} runs")


if __name__ == "__main__":
    main()
