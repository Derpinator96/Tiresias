"""Workload windows for drift detection (doc, Detailed component specs, Miner: drift). Private side.

A background thread samples pg_stat_statements every miner.drift_sample_s: cumulative calls and
total time per template code. A window of length W runs between two consecutive multiples of W
in Unix time; its totals are the difference of the latest samples at or before each boundary, so
a boundary is late by up to one sample period. Only each template's share of the window's time
and calls leaves the gateway: no SQL, no absolute totals.

ponytail: samples live in gateway memory only, so a gateway restart starts the history again.
Persist them next to the ledger if drift must survive restarts.
"""
from __future__ import annotations

import bisect
import math
import sys
import threading
import time
from collections import deque
from typing import Callable

from common.config import cfg

Totals = dict[str, tuple[float, float]]          # template_id -> (calls, total_ms), cumulative


def window_s() -> int:
    """The configured window length: miner.drift_window_<mode>_s, mode demo or production."""
    return int(cfg(f"miner.drift_window_{cfg('miner.drift_window_mode')}_s"))


def shares(before: Totals, after: Totals) -> dict[str, dict]:
    """Each template's share of the time and calls between two cumulative samples. A counter that
    went down was reset (pg_stat_statements_reset), so its whole current value counts."""
    delta = {}
    for tid, (calls, ms) in after.items():
        c0, m0 = before.get(tid, (0, 0.0))
        dc, dm = (calls - c0, ms - m0) if calls >= c0 else (calls, ms)
        if dc > 0:
            delta[tid] = (dc, dm)
    calls_total = sum(c for c, _ in delta.values())
    ms_total = sum(m for _, m in delta.values()) or 1.0
    return {tid: {"time_share": round(m / ms_total, 4), "call_share": round(c / calls_total, 4)}
            for tid, (c, m) in sorted(delta.items())}


class Windows:
    def __init__(self, read_totals: Callable[[], Totals]):
        self.read_totals = read_totals
        self.samples: deque[tuple[float, Totals]] = deque()
        self._lock = threading.Lock()

    def sample(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        totals = self.read_totals()
        keep_s = (int(cfg("miner.drift_windows_kept")) + 1) * window_s()
        with self._lock:
            self.samples.append((now, totals))
            while self.samples[0][0] < now - keep_s:
                self.samples.popleft()

    def start(self) -> None:
        def loop():
            while True:
                try:
                    self.sample()
                except Exception as e:                   # pg-prod restarting or reseeding
                    print(f"drift sample failed: {type(e).__name__}: {e}", file=sys.stderr)
                time.sleep(float(cfg("miner.drift_sample_s")))
        threading.Thread(target=loop, name="drift-sampler", daemon=True).start()

    def windows(self, length_s: int) -> list[dict]:
        """Closed windows of length_s seconds, oldest first, at most miner.drift_windows_kept:
        [{"end": unix seconds, "templates": {template_id: {"time_share", "call_share"}}}]."""
        with self._lock:
            samples = list(self.samples)
        if not samples:
            return []
        times = [t for t, _ in samples]

        def at(boundary: float) -> Totals:
            return samples[bisect.bisect_right(times, boundary) - 1][1]

        first = math.ceil(samples[0][0] / length_s)
        last = math.floor(samples[-1][0] / length_s)
        out = [{"end": (k + 1) * length_s, "templates": shares(at(k * length_s), at((k + 1) * length_s))}
               for k in range(first, last)]
        return out[-int(cfg("miner.drift_windows_kept")):]
