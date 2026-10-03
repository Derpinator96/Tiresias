"""Adversarial leak test units: scoring on toy guesses, the random-guess baseline, the AI-side
prompt and parser, and that the adversary's request carries no tools. No services needed.
The live run is `make adversarial` (see privacy_tests/NOTES.md)."""
import json

import httpx
import pytest

from agent import adversary
from agent import llm
from privacy_tests import adversarial as adv

TRUTH = {"t_00000001": ("table", "sales"), "c_00000002": ("column", "transaction_date"),
         "c_00000003": ("column", "amount"), "c_00000004": ("column", "segment")}


@pytest.mark.parametrize("guess,real,expected", [
    ("sales", "sales", "exact"),
    (" `Sales` ", "sales", "exact"),
    ("orders.order_date", "transaction_date", "synonym"),
    ("Order Date", "transaction_date", "synonym"),
    ("total_amount", "amount", "synonym"),
    ("price", "amount", "none"),
    ("", "sales", "none"),
])
def test_match_exact_synonym_none(guess, real, expected):
    assert adv.match(guess, real) == expected


def test_score_counts_toy_guesses_and_skipped_codes_score_none():
    sc = adv.score({"t_00000001": "orders", "c_00000002": "transaction_date", "c_00000003": "price"}, TRUTH)
    assert sc["all"] == {"codes": 4, "exact": 1, "synonym": 1, "exact_rate": 0.25, "rate": 0.5}
    assert sc["table"]["synonym"] == 1 and sc["column"]["exact"] == 1
    assert [(r["code"], r["match"]) for r in sc["per_code"]] == [  # sorted by code
        ("c_00000002", "exact"), ("c_00000003", "none"), ("c_00000004", "none"), ("t_00000001", "synonym")]
    assert "sales" not in json.dumps(sc["per_code"])            # no real names in the per-code rows


def test_baseline_is_the_expected_hit_rate_of_a_random_common_name(monkeypatch):
    monkeypatch.setattr(adv, "COMMON", {"table": ["sales", "orders", "users", "logs"], "column": ["amount", "id"]})
    b = adv.baseline({"t_00000001": ("table", "sales"), "c_00000003": ("column", "amount")})
    assert b["exact_rate"] == round((1 / 4 + 1 / 2) / 2, 4)        # sales 1 of 4, amount 1 of 2
    assert b["rate"] == round((2 / 4 + 1 / 2) / 2, 4)              # orders is a synonym of sales


def test_parse_guesses_reads_fenced_json_and_ignores_unasked_codes():
    text = 'Here:\n```json\n{"t_00000001": "orders", "c_00000002": 5, "c_99999999": "x"}\n```'
    assert adversary.parse_guesses(text, ["t_00000001", "c_00000002"]) == {"t_00000001": "orders"}
    assert adversary.parse_guesses("no idea", ["t_00000001"]) == {}
    assert adversary.parse_guesses("{broken", ["t_00000001"]) == {}


def test_select_puts_llm_bodies_first_and_skips_what_overflows_the_budget():
    ps = [{"body": "a" * 4, "destination": "ai"}, {"body": "b" * 4, "destination": "llm"}, {"body": "c", "destination": "ai"}]
    assert [p["body"] for p in adversary.select(ps, 6)] == ["bbbb", "c"]
    assert [p["body"] for p in adversary.select(ps, 9)] == ["bbbb", "aaaa", "c"]


class ScriptedLLM:
    model = "scripted"
    last_entry = {"payload_id": "pay_0000abcd"}

    def __init__(self):
        self.calls = []

    def generate(self, system, contents, declarations, on_event=None):
        self.calls.append((system, contents, declarations))
        return {"candidates": [{"content": {"parts": [{"text": '{"t_00000001": "orders", "c_00000002": "order_date"}'}]}}]}


def test_run_sends_one_tool_free_request_listing_every_code():
    payloads = [{"body": json.dumps({"sql": "SELECT SUM(c_00000003) FROM t_00000001"}), "destination": "ai"},
                {"body": json.dumps({"contents": "c_00000002 >= ?"}), "destination": "llm"}]
    model = ScriptedLLM()
    out = adversary.run(payloads, model)
    (system, contents, declarations), = model.calls
    assert declarations == [] and "guess" in system
    assert "Codes to name: c_00000002, c_00000003, t_00000001" in contents[0]["parts"][0]["text"]
    assert out["codes"] == ["c_00000002", "c_00000003", "t_00000001"]
    assert out["guesses"] == {"t_00000001": "orders", "c_00000002": "order_date"}
    assert out["material"]["payloads_sent"] == 2 and out["material"]["llm_payloads_sent"] == 1
    assert out["llm_payload_id"] == "pay_0000abcd"


def test_run_leaves_out_an_earlier_adversary_request():
    earlier = {"body": json.dumps({"systemInstruction": {"parts": [{"text": adversary.SYSTEM}]}, "x": "t_00000009"}),
               "destination": "llm"}
    model = ScriptedLLM()
    out = adversary.run([earlier, {"body": "t_00000001", "destination": "ai"}], model)
    assert out["codes"] == ["t_00000001"] and out["material"]["payloads_in_window"] == 1


def test_run_without_codes_makes_no_llm_call():
    model = ScriptedLLM()
    assert adversary.run([], model)["codes"] == [] and model.calls == []


def test_tool_free_request_has_no_tools_field_and_is_scanned_first(monkeypatch):
    scanned, sent = [], []
    monkeypatch.setattr(llm.gw, "post", lambda path, body: scanned.append(body) or
                        {"payload_id": "pay_00000001", "verdict": "allow", "canary_hits": []})
    reply = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
    g = llm.GeminiREST("m", "k", httpx.MockTransport(lambda r: sent.append(r.content.decode()) or httpx.Response(200, json=reply)))
    g.generate("sys", [{"role": "user", "parts": [{"text": "x"}]}], [])
    assert sent == [scanned[0]["body"]] and g.last_entry["payload_id"] == "pay_00000001"
    assert "tools" not in json.loads(sent[0]) and "toolConfig" not in json.loads(sent[0])


def test_dashboard_label_matches_the_module():
    from dashboard import data
    assert data.LABELS["adversarial"] == adv.LABEL
