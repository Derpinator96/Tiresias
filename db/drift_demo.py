"""make drift-demo: switch the workload mix mid-demo (doc, demo flow step 9). Private side.

Runs as the application role on pg-prod, in three phases of whole drift windows:
1. before: workload.drift_before in turn (the seeded mix) for 1 window;
2. rollout: drift_before plus drift_after in turn for 1 window (Q4 rolls out);
3. after: workload.drift_after in turn (Q4 heavy) for miner.drift_windows_required + 1 windows.
The rollout window is what lets the doc's consecutive-window rule fire for any window alignment
(see miner/drift.py). The miner on the AI side detects the drift from the gateway's windows; the
dashboard's drift panel then re-runs the search with the new weights.

    python -m db.drift_demo      # about 10 minutes with the demo window of 120 s
"""
from __future__ import annotations

import itertools
import os
import time

import psycopg

from common.config import cfg
from db import run_q1, workload
from gateway.windows import window_s


def run_mix(conn: psycopg.Connection, mix: list[str], seconds: float) -> int:
    """Run the named queries in turn until `seconds` have passed. Returns queries run."""
    end, n = time.monotonic() + seconds, 0
    for name in itertools.cycle(mix):
        if time.monotonic() >= end:
            return n
        conn.execute(workload.QUERIES[name]()).fetchall()
        n += 1


def phases(window: float) -> list[tuple[str, list[str], float]]:
    before, after = list(cfg("workload.drift_before")), list(cfg("workload.drift_after"))
    return [("before", before, window), ("rollout", before + after, window),
            ("after", after, (int(cfg("miner.drift_windows_required")) + 1) * window)]


def run(dsn: str, window: float) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name, mix, seconds in phases(window):
            print(f"{time.strftime('%H:%M:%S')} {name}: {', '.join(mix)} for {seconds:.0f} s", flush=True)
            print(f"  {run_mix(conn, mix, seconds)} queries", flush=True)
    print(f"{time.strftime('%H:%M:%S')} done. Check the drift panel on the dashboard.", flush=True)


if __name__ == "__main__":
    run(run_q1.app_dsn(os.environ["PROD_DSN"]), window_s())
