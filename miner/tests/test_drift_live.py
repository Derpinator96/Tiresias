"""Drift component test on the live stack (tools container, after `make seed`).

Switching to Q4 triggers drift within 2 windows, and the search in the running ai process then
picks an index that Q4's HypoPG plan uses; its Q-table is kept, not reset. The test uses a short
window through /ai/mine's test-only window_s; the configured demo window is unchanged. Q4's
pg_stat_statements entry is reset before and after, so later suites see the default workload.
"""
import os
import time

import httpx
import psycopg
import pytest

from common.config import cfg
from db import drift_demo, run_q1

W = 15                           # test-only window, seconds (the demo uses miner.drift_window_demo_s)
TIMEOUT = 600


def reset_q4():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as c:
        rows = c.execute("SELECT queryid FROM pg_stat_statements WHERE query LIKE 'SELECT c.segment, s.transaction_date%'").fetchall()
        for (qid,) in rows:
            c.execute("SELECT pg_stat_statements_reset(0, 0, %s)", (qid,))


@pytest.fixture
def clean_q4():
    reset_q4()
    yield
    reset_q4()


def ai(path, body):
    r = httpx.post(os.environ["AI_URL"] + path, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def gateway(path, body):
    r = httpx.post(os.environ["GATEWAY_URL"] + path, json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def q4_plan(config, q4):
    return next(p for p in gateway("/v1/simulate/hypopg", config)["plans"] if p["template_id"] == q4)


def test_switch_to_q4_triggers_drift_and_search_adapts_without_restart(clean_q4):
    before_rl = ai("/ai/rl/run", {})
    before_mix, after_mix = list(cfg("workload.drift_before")), list(cfg("workload.drift_after"))
    b0 = int(time.time() // W + 1) * W
    time.sleep(b0 - time.time())
    with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
        for mix, until in [(before_mix, b0 + 2 * W), (before_mix + after_mix, b0 + 3 * W), (after_mix, b0 + 4 * W)]:
            drift_demo.run_mix(conn, mix, until - time.time())
    time.sleep(max(0.0, b0 + 4 * W - time.time()) + 2 * float(cfg("miner.drift_sample_s")))

    d = ai("/ai/mine", {"window_s": W})["drift"]
    dist = {x["end"]: x["js_distance"] for x in d["distances"]}
    print("distances after b0:", {k - b0: v for k, v in dist.items() if k > b0})
    theta = cfg("miner.drift_js_threshold")
    assert dist[b0 + 2 * W] <= theta                       # the stable mix raises no alarm
    assert dist[b0 + 3 * W] > theta and dist[b0 + 4 * W] > theta
    assert d["triggered"] and d["triggered_at"] == b0 + 4 * W     # 2 windows after the switch began

    weights = d["weights"]
    q4 = max(weights, key=weights.get)
    text = gateway("/v1/answers/dehash", {"question_id": "qn_00000000", "text": q4, "numbers": []})["text"]
    assert "c.segment" in text, text

    after_rl = ai("/ai/rl/run", {"weights": weights})
    print("before:", before_rl["config"]["actions"], "after:", after_rl["config"]["actions"])
    assert after_rl["q_entries"] >= before_rl["q_entries"]     # same Q-table, kept and extended
    # Index actions only: since step 23 a config may also hold rewrites, which carry no cand_id.
    def cands(rl):
        return {a["cand_id"] for a in rl["config"]["actions"] if a["type"] == "add_index"}
    new = cands(after_rl) - cands(before_rl)
    assert new, "the search did not change its recommendation after drift"
    empty = {"config_id": "cfg_00000000", "search": "greedy", "actions": []}
    plan_before, plan_after = q4_plan(empty, q4), q4_plan(after_rl["config"], q4)
    assert not any(n.get("index") for n in plan_before["nodes"])
    assert any(n.get("index") for n in plan_after["nodes"]), "Q4's plan does not use the new index"
    assert plan_after["nodes"][0]["est_cost"] < plan_before["nodes"][0]["est_cost"]
