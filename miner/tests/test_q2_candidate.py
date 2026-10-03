"""Miner component test for Q2 (tools container, after make seed): with the rewritten shapes,
the index that only helps after Q2's date_trunc rewrite is proposed. Codes only on the AI side;
the test translates them through the gateway's dehash endpoint."""
import os

import httpx

from agent.api import mine


def test_index_that_only_helps_after_the_rewrite_is_proposed():
    cands = mine()["candidates"]
    text = "\n".join(" ".join([c["table"]] + c["columns"]) for c in cands)
    names = httpx.post(os.environ["GATEWAY_URL"] + "/v1/answers/dehash",
                       json={"question_id": "qn_00000000", "text": text, "numbers": []}, timeout=30).json()["text"]
    assert "sales store_id transaction_date" in names.splitlines(), names
