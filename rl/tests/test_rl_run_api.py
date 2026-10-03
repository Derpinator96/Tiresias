"""Component test of /ai/rl/run on the seeded stack (tools container, after make seed): rewrite
actions are offered and chosen live, and the final configuration is the best twin measurement
of the top configurations. Runs over HTTP, so it also exercises the ai service's caches."""
import os

import httpx

from common.config import cfg
from contracts.validate import errors
from rl import search


def test_rl_run_rechecks_top_configs_on_the_twin_and_uses_rewrites():
    r = httpx.post(os.environ["AI_URL"] + "/ai/rl/run", json={}, timeout=900)
    assert r.status_code == 200, r.text
    rl = r.json()
    assert errors("Config", rl["config"]) == [] and rl["label"] == search.LABEL
    # Only the gateway's matching pairs were checked; Q2's date_trunc is TestedOnly, the OR
    # query's rewrite Verified (VeriEQL can encode it).
    status = {c["rule_id"]: c["status"] for c in rl["rewrites"]}
    assert status == {"date_trunc_eq_to_range": "TestedOnly", "or_same_column_to_in": "Verified"}
    rules = {a["rule_id"] for a in rl["config"]["actions"] if a["type"] == "rewrite"}
    assert "date_trunc_eq_to_range" in rules
    # Top configurations: each measured on the twin, the chosen one has the best score.
    top = rl["top_configs"]
    assert 0 < len(top) <= cfg("rl.configs_verified_on_twin")
    assert rl["final_choice"] == "best measured on the twin"
    measured = [e for e in top if "score" in e]
    chosen = [e for e in top if e["chosen"]]
    assert len(chosen) == 1 and chosen[0]["score"] == max(e["score"] for e in measured)
    assert chosen[0]["twin"]["templates"] and chosen[0]["measured_drop"] > 0
    assert sorted(map(search._akey, chosen[0]["actions"])) == sorted(map(search._akey, rl["config"]["actions"]))
