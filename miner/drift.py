"""Workload drift (doc, Component 2 step 6 and Detailed component specs, Miner: drift). REAL.

Input: the gateway's closed windows, each holding every template's share of the window's time
and calls (codes and numbers only). Per the doc: compare consecutive windows' shares of total
time with the Jensen-Shannon distance (base 2, so 0 = identical mix and 1 = disjoint mixes; the
doc's threshold applies to the distance, not the divergence) and trigger when the distance is
above miner.drift_js_threshold for miner.drift_windows_required windows in a row. Windows with
no queries carry no mix and are skipped.

The doc's rule compares consecutive windows, so a sudden permanent switch produces one large
distance and then small ones: it triggers only when the switch lands inside a window, which then
differs from both neighbours. `make drift-demo` rolls Q4 out over one window, which triggers for
any window alignment. Flagged for a human in miner/NOTES.md.

The new template weights for the search are the latest window's call shares (doc, Component 4:
the state includes how often each template runs).

Checked in the pinned image: scipy 1.17.1, jensenshannon(p, q, base=None, *, axis=0,
keepdims=False) returns the distance and normalises p and q.
"""
from __future__ import annotations

import math

from scipy.spatial.distance import jensenshannon

from common.config import cfg


def js_distance(p: dict[str, float], q: dict[str, float]) -> float:
    keys = sorted(set(p) | set(q))
    d = float(jensenshannon([p.get(k, 0.0) for k in keys], [q.get(k, 0.0) for k in keys], base=2))
    return 0.0 if math.isnan(d) else d          # identical mixes can round to sqrt of a tiny negative


def state(windows: list[dict], window_s: int) -> dict:
    """Drift state over the gateway's windows (oldest first). `triggered` stays true while the
    window that completed the trigger is among the kept windows (miner.drift_windows_kept)."""
    threshold, required = float(cfg("miner.drift_js_threshold")), int(cfg("miner.drift_windows_required"))
    mixes = [w for w in windows if w["templates"]]
    distances, run, triggered_at = [], 0, None
    for a, b in zip(mixes, mixes[1:]):
        d = js_distance({t: s["time_share"] for t, s in a["templates"].items()},
                        {t: s["time_share"] for t, s in b["templates"].items()})
        distances.append({"end": b["end"], "js_distance": round(d, 4)})
        run = run + 1 if d > threshold else 0
        if run >= required:
            triggered_at = b["end"]
    return {
        "window_s": window_s, "threshold": threshold, "windows_required": required,
        "windows": len(mixes), "distances": distances,
        "current_js_distance": distances[-1]["js_distance"] if distances else None,
        "triggered": triggered_at is not None, "triggered_at": triggered_at,
        "weights": {t: s["call_share"] for t, s in mixes[-1]["templates"].items()} if mixes else {},
    }
