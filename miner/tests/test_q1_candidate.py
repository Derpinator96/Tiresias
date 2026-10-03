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
    # Q2 (step 21) holds most slow time, so its candidates rank first; find Q1's by its real
    # names (human-approved test change, 2026-10-03).
    named = {dehash(" ".join([c["table"]] + c["columns"])): c for c in composite}
    assert "sales region_id transaction_date" in named, named      # region first, then date
    assert "sales transaction_date region_id" not in named
    assert named["sales region_id transaction_date"]["support"] >= 0.05


def dehash(text: str) -> str:
    answer = {"question_id": "qn_00000000", "text": text, "numbers": []}
    return httpx.post(os.environ["GATEWAY_URL"] + "/v1/answers/dehash", json=answer, timeout=30).json()["text"]
