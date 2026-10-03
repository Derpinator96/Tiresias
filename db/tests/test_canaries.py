"""Canaries must not collide with ordinary text. The scanner matches any 6-character fragment
of a canary, case-insensitively, so a fragment that is part of an English word blocks
legitimate payloads (first live LLM run: "recommended" contains "commen" from a canary that
held the word COMMENT). No database needed."""
import re

import pytest

from agent import prompts
from agent.tools import DECLARATIONS
from common.config import REPO_ROOT, cfg
from db import canaries

K = cfg("gateway.canary_fragment_chars")


def fragments(value: str) -> set[str]:
    v = value.lower()
    return {v[i:i + K] for i in range(max(1, len(v) - K + 1))}


def english_corpus() -> str:
    """The architecture doc as a sample of the project's English, with the doc's own canary
    examples removed (it quotes CANARY_7731@corp.com and 7731.77 when describing them)."""
    text = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8").lower()
    text = re.sub(r"canary[\w@.]*", " ", text)
    return text.replace("7731.77", " ")


AGENT_TEXT = " ".join([
    prompts.system_prompt(cfg("llm.max_tool_calls")),
    prompts.user_turn("qn_00000000", ["q_00000000"]),
    prompts.checker_feedback(["1"]),
    str(DECLARATIONS),
]).lower()


@pytest.mark.parametrize("c", canaries.ALL, ids=lambda c: c.kind + ":" + c.canary_id)
def test_no_fragment_in_agent_prompts_or_tools(c):
    assert not [f for f in fragments(c.value) if f in AGENT_TEXT]


@pytest.mark.parametrize("c", canaries.ALL, ids=lambda c: c.kind + ":" + c.canary_id)
def test_no_fragment_in_ordinary_english(c):
    corpus = english_corpus()
    assert not [f for f in fragments(c.value) if f in corpus]
