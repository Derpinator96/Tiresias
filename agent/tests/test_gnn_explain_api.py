"""Component test of POST /ai/gnn/explain on the seeded stack (tools container, after make seed).
No LLM is involved: the endpoint runs the gnn_explain tool directly."""
import os

import httpx

from contracts.validate import errors


def ai(path, body=None):
    url = os.environ["AI_URL"] + path
    return httpx.post(url, json=body, timeout=120) if body is not None else httpx.get(url, timeout=120)


def test_explain_returns_the_tool_result_labelled_with_the_serving_estimator():
    slow = httpx.get(os.environ["GATEWAY_URL"] + "/v1/templates/slow", timeout=120).json()
    tid = slow[0]["template_id"]
    r = ai("/ai/gnn/explain", {"template_id": tid})
    assert r.status_code == 200, r.text
    x = r.json()
    serving = ai("/ai/gnn/estimator").json()
    assert (x["estimator"], x["label"]) == (serving["estimator"], serving["label"])
    assert x["top_nodes"] and all(0 <= n["predicted_share_pct"] <= 100 for n in x["top_nodes"])
    assert x["predicted_total_ms"] > 0 and isinstance(x["misestimates"], list)
    plan = httpx.get(os.environ["GATEWAY_URL"] + f"/v1/templates/{tid}/plans", timeout=120).json()[0]
    assert errors("HashedPlan", plan) == []
    assert {n["node_id"] for n in x["top_nodes"]} <= {n["node_id"] for n in plan["nodes"]}


def test_explain_rejects_a_missing_or_unknown_template():
    assert ai("/ai/gnn/explain", {}).status_code == 400
    assert ai("/ai/gnn/explain", {"template_id": "q_00000000"}).status_code == 404
