"""scripts/record_ask.py without services: the record keeps hashed data only and is refused
when a forbidden name or canary would reach the public site."""
import json

from db import canaries
from scripts import record_ask

BODY = {"status": "ok", "answer": {"text": "Index t_0a1b2c3d (c_11111111, c_22222222): 303.6 to 98.3 ms.",
                                    "numbers": [{"value": "303.6", "tool_call_id": "tc_1"}]},
        "unmatched": [], "tool_calls": 5,
        "config": {"config_id": "cfg_00000001", "search": "q_learning", "actions": [{"type": "add_index", "table": "t_0a1b2c3d", "columns": ["c_11111111"]}]},
        "simulation": {"config_id": "cfg_00000001", "source": "twin", "runs": 5, "write_ms_delta": 0.03, "storage_mb_delta": 68.0,
                       "templates": [{"template_id": "q_00000001", "before_ms": 303.6, "after_ms": 98.3, "speedup_pct": 67.6}]}}
LEDGER = {"outbound_payloads": 40, "outbound_canary_hits": 0}


def doc(body=BODY, events=("tool get_slow_templates -> tc_1",)):
    return record_ask.build("qn_00000001", ["q_00000001"], body, list(events), {"provider": "gemini", "model": "m"},
                            LEDGER, {**LEDGER, "outbound_payloads": 45}, "a" * 40, "2026-10-04T00:00:00Z")


def test_record_keeps_hashed_fields_and_ledger_delta(tmp_path):
    out = tmp_path / "ask_replay.json"
    assert record_ask.write(doc(), out) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["recorded"] is True and saved["question_id"] == "qn_00000001"
    assert saved["ledger"] == {"payloads_before": 40, "payloads_after": 45, "canary_hits_after": 0}
    assert "question" not in saved and saved["simulation"]["templates"][0] == {"template_id": "q_00000001", "before_ms": 303.6, "after_ms": 98.3}


def test_refuses_a_real_name(tmp_path):
    out = tmp_path / "ask_replay.json"
    leaked = {**BODY, "answer": {"text": "Index on sales (region_id).", "numbers": []}}
    assert record_ask.write(doc(leaked), out) == 1
    assert not out.exists()


def test_refuses_a_canary_value(tmp_path):
    out = tmp_path / "ask_replay.json"
    assert record_ask.write(doc(events=[f"tool x -> {canaries.ALL[0].value}"]), out) == 1
    assert not out.exists()
