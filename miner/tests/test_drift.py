"""Drift unit tests: Jensen-Shannon distance on known mixes, the 2-window trigger, and the
gateway's windows plus the miner's rule on a simulated workload switch (no database)."""
import math

import pytest

from common.config import cfg
from gateway.windows import Windows
from miner.drift import js_distance, state

A, B, C = "q_0000000a", "q_0000000b", "q_0000000c"


def test_js_distance_on_known_mixes():
    assert js_distance({A: 0.5, B: 0.5}, {A: 0.5, B: 0.5}) == 0.0
    assert js_distance({A: 1.0}, {B: 1.0}) == pytest.approx(1.0)          # disjoint mixes
    # P = (1, 0), Q = (0.5, 0.5), M = (0.75, 0.25), base 2:
    # JSD = (log2(4/3) + 0.5 log2(2/3) + 0.5 log2(2)) / 2, distance = sqrt(JSD).
    jsd = (math.log2(4 / 3) + 0.5 * math.log2(2 / 3) + 0.5) / 2
    assert js_distance({A: 1.0}, {A: 0.5, B: 0.5}) == pytest.approx(math.sqrt(jsd))
    assert js_distance({A: 1.0}, {A: 0.5, B: 0.5}) == pytest.approx(0.5579, abs=1e-4)


def win(end, mix):
    return {"end": end, "templates": {t: {"time_share": s, "call_share": s} for t, s in mix.items()}}


OLD, NEW = {A: 0.5, B: 0.5}, {C: 1.0}
HALF = {A: 0.25, B: 0.25, C: 0.5}


def test_one_window_above_threshold_does_not_trigger():
    s = state([win(1, OLD), win(2, NEW), win(3, NEW), win(4, NEW)], 1)
    assert [d["js_distance"] for d in s["distances"]] == [1.0, 0.0, 0.0]
    assert s["current_js_distance"] == 0.0 and not s["triggered"]


def test_two_windows_in_a_row_trigger():
    s = state([win(1, OLD), win(2, OLD), win(3, HALF), win(4, NEW)], 1)
    assert s["distances"][-1]["js_distance"] > cfg("miner.drift_js_threshold")
    assert s["triggered"] and s["triggered_at"] == 4
    assert s["weights"] == {C: 1.0}                                        # latest window's call shares


def test_idle_windows_carry_no_mix_and_are_skipped():
    s = state([win(1, OLD), win(2, {}), win(3, OLD)], 1)
    assert s["windows"] == 2 and s["distances"] == [{"end": 3, "js_distance": 0.0}]
    assert state([], 1)["current_js_distance"] is None


# ---- gateway windows plus the miner's rule on a simulated switch ---------------------------
def cumulative(phases):
    """read_totals for a simulated clock: phases are (start, end, {template: ms per second});
    each template runs one call per 100 ms of its time."""
    clock = {"t": 0.0}

    def read():
        out = {}
        for start, end, rates in phases:
            dt = max(0.0, min(clock["t"], end) - start)
            for tid, ms_per_s in rates.items():
                c, m = out.get(tid, (0.0, 0.0))
                out[tid] = (c + dt * ms_per_s / 100, m + dt * ms_per_s)
        return out
    return clock, read


def run_switch(offset: float, rollout: bool, w: int = 100, sample_s: int = 2):
    """Before mix, then (optionally) one window of rollout, then the Q4-heavy mix. The rollout
    starts `offset` windows after a window boundary."""
    r0 = 10 * w + offset * w
    before, after = {A: 500.0, B: 500.0}, {A: 140.0, C: 860.0}
    rollout_mix = {k: (before.get(k, 0) + after.get(k, 0)) / 2 for k in {A, B, C}}
    if rollout:
        phases = [(r0 - 3 * w, r0, before), (r0, r0 + w, rollout_mix), (r0 + w, r0 + 5 * w, after)]
    else:
        phases = [(r0 - 3 * w, r0, before), (r0, r0 + 5 * w, after)]
    clock, read = cumulative(phases)
    ws = Windows(read)
    t = r0 - 4 * w
    while t <= r0 + 5 * w:
        clock["t"] = t
        ws.sample(now=t)
        t += sample_s
    return r0, w, state(ws.windows(w), w)


@pytest.mark.parametrize("offset", [0.0, 0.25, 0.5, 0.75, 0.99])
def test_rollout_over_one_window_triggers_at_any_alignment(offset):
    r0, w, s = run_switch(offset, rollout=True)
    assert s["triggered"], s["distances"]
    # At most 2 windows after the switch to the Q4 mix is complete (rollout end = r0 + w).
    assert r0 < s["triggered_at"] <= r0 + 3 * w
    assert max(s["weights"], key=s["weights"].get) == C


def test_doc_rule_misses_a_sudden_switch_on_a_window_boundary():
    """Documents the doc's consecutive-window rule (flagged in miner/NOTES.md): a permanent
    switch exactly at a boundary gives one large distance, then the new mix compares equal to
    itself, so it never stays above the threshold for 2 windows."""
    _, _, s = run_switch(0.0, rollout=False)
    assert max(d["js_distance"] for d in s["distances"]) > cfg("miner.drift_js_threshold")
    assert not s["triggered"]
