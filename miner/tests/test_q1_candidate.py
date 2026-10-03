"""Miner component test against the live gateway (run in the tools container after
`make seed`). The miner sees only codes; the test translates the winning candidate back to
real names through the gateway's dehash endpoint, as the dashboard would."""
import httpx
import os

from agent.api import mine
from contracts.validate import errors


def test_q1_candidate_is_region_then_date():
    result = mine()
    cands = result["candidates"]
    assert cands, "no candidates"
    for c in cands:
        assert errors("Candidate", c) == []
    composite = [c for c in cands if len(c["columns"]) == 2]
    assert composite, cands
    top = composite[0]
    answer = {"question_id": "qn_00000000", "text": " ".join([top["table"]] + top["columns"]), "numbers": []}
    names = httpx.post(os.environ["GATEWAY_URL"] + "/v1/answers/dehash", json=answer, timeout=30).json()["text"]
    assert names == "sales region_id transaction_date"
    assert top["support"] >= 0.05
