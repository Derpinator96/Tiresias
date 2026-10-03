"""Scenario (doc acceptance, Miner and RL agent): switching to the Q4 workload triggers drift
within 2 windows, the search adapts without restarting ai, and greedy is reported next to it.
No LLM call. Run in the tools container after make up and make seed (make e2e-offline).

miner/tests/test_drift_live.py proves the same chain with a test-only 15 s window. This
scenario adds what that test does not cover: the configured window (gateway.windows.window_s,
miner.drift_window_demo_s in demo mode), read through /ai/mine with no override, the phases of
make drift-demo (db/drift_demo.py), and the greedy result reported next to the post-drift
search. Its helpers are reused, not copied.

Timeline (W = the configured window, b0 the next multiple of W): the seeded mix runs from now
to b0 + W, Q4 rolls out over [b0 + W, b0 + 2W] (the switch begins at b0 + W), the Q4-heavy mix
runs over [b0 + 2W, b0 + 3W]. Drift must trigger at b0 + 3W, the second window after the switch
began. About 3.5 W plus two searches: over tests.fast_suite_limit_s by design (doc, Testing
plan: the scenario layer runs under 15 min), so no elapsed limit is asserted; it is printed.
"""
import os
import time

import psycopg

from common.config import cfg
from db import drift_demo, run_q1
from e2e.test_invented_number import wait_for_ai
from gateway.windows import window_s
from miner.tests.test_drift_live import ai, gateway, q4_plan, reset_q4


def cands(rl: dict) -> set[str]:
    return {a["cand_id"] for a in rl["config"]["actions"] if a["type"] == "add_index"}


def test_q4_drift_on_the_configured_window():
    wait_for_ai()                     # make e2e-offline has just put ai back in online mode
    started = time.time()
    reset_q4()
    try:
        w = window_s()
        before_rl = ai("/ai/rl/run", {})
        before_mix, after_mix = list(cfg("workload.drift_before")), list(cfg("workload.drift_after"))
        b0 = int(time.time() // w + 1) * w
        with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
            for mix, until in [(before_mix, b0 + w), (before_mix + after_mix, b0 + 2 * w), (after_mix, b0 + 3 * w)]:
                drift_demo.run_mix(conn, mix, until - time.time())
        time.sleep(max(0.0, b0 + 3 * w - time.time()) + 2 * float(cfg("miner.drift_sample_s")))

        d = ai("/ai/mine", {})["drift"]                      # no override: the configured window
        assert d["window_s"] == w
        dist = {x["end"]: x["js_distance"] for x in d["distances"]}
        print(f"window {w} s; distances after b0:", {k - b0: v for k, v in dist.items() if k > b0})
        theta = cfg("miner.drift_js_threshold")
        assert dist[b0 + 2 * w] > theta and dist[b0 + 3 * w] > theta
        assert d["triggered"] and d["triggered_at"] == b0 + 3 * w    # 2 windows after the switch began

        weights = d["weights"]
        q4 = max(weights, key=weights.get)
        text = gateway("/v1/answers/dehash", {"question_id": "qn_00000000", "text": q4, "numbers": []})["text"]
        assert "c.segment" in text, text

        after_rl = ai("/ai/rl/run", {"weights": weights})
        assert after_rl["q_entries"] >= before_rl["q_entries"]        # same ai process, Q-table kept
        assert cands(after_rl) - cands(before_rl), "the search did not change its recommendation after drift"
        empty = {"config_id": "cfg_00000000", "search": "greedy", "actions": []}
        assert any(n.get("index") for n in q4_plan(after_rl["config"], q4)["nodes"]), "Q4's plan does not use the new index"
        assert not any(n.get("index") for n in q4_plan(empty, q4)["nodes"])

        # Greedy on the same post-drift weights, reported next to the search's result.
        g = after_rl["greedy"]
        assert g["cand_ids"] and isinstance(g["predicted_ms"], float) and isinstance(g["same_as_rl"], bool)
        print(f"after drift: search {sorted(cands(after_rl))} predicted {after_rl['final_predicted_ms']} ms; "
              f"greedy {g['cand_ids']} predicted {g['predicted_ms']} ms; same as search: {g['same_as_rl']}")
    finally:
        reset_q4()
    print(f"drift scenario: {time.time() - started:.0f} s")
