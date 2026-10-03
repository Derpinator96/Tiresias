"""scripts/llm_bench.py selection and fixture rules (no services needed)."""
import pytest

from common.config import cfg
from scripts import llm_bench

LISTED = ["deepseek-ai/deepseek-r1", "meta/llama-3.3-70b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct",
          "nvidia/llama-3.3-nemotron-super-49b-v1", "nvidia/nv-embedqa-e5-v5", "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
          "nvidia/llama-3.1-nemoguard-8b-content-safety", "mistralai/mixtral-8x7b-instruct-v0.1",
          "nvidia/nemotron-mini-4b-instruct", "nvidia/llama-3.1-nemotron-70b-reward"]


def test_candidates_prefer_nemotron_and_skip_reasoning_only_and_non_chat_models():
    c = llm_bench.candidates(LISTED)
    assert len(c) == cfg("llm.nim.bench_candidates")
    assert all("nemotron" in m for m in c)
    assert not any(x in m for m in c for x in ("r1", "embed", "reward", "-vl-", "safety"))
    assert c[0] == "nvidia/llama-3.1-nemotron-70b-instruct"        # family and instruct ranked first


def test_best_is_the_passing_run_with_fewest_errors_then_fastest():
    rows = [{"model": "a", "http": 200, "ok": True, "tool_call_errors": ["x"], "llm_seconds": 1.0},
            {"model": "b", "http": 200, "ok": True, "tool_call_errors": [], "llm_seconds": 9.0},
            {"model": "c", "http": 200, "ok": True, "tool_call_errors": [], "llm_seconds": 3.0},
            {"model": "d", "http": 200, "ok": False, "tool_call_errors": [], "llm_seconds": 0.5},
            {"model": "e", "http": 503, "ok": False, "error": "x"}]
    assert llm_bench.best(rows)["model"] == "c"
    assert llm_bench.best(rows[3:]) is None


def test_a_fixture_with_a_canary_is_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_bench, "FIXTURES", tmp_path)
    with pytest.raises(RuntimeError, match="canary"):
        llm_bench.write_fixture({"provider": "nim", "model": "m", "exchanges": [{"response": "CANARY_ASK_7731"}]})
    assert not list(tmp_path.iterdir())
