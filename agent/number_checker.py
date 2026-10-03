"""Number checker (doc, LLM tools and system rules). Before an answer is shown, every number
in it must carry a tool-call tag, [tc_xxxxxxxx], and appear in that tool call's result.

- Digits inside codes (t_, c_, q_, i_, p_, tc_, cand_, cfg_, qn_ plus 8 hex) are not numbers.
- A written number matches a result value if it equals that value rounded to the number of
  decimals written (24.3 matches 24.297). Thousands separators are allowed.
- An untagged number, or one absent from its cited result, is unmatched and blocks the answer.
"""
from __future__ import annotations

import re

CODE_RE = re.compile(r"\b(?:t|c|q|i|p|tc|cand|cfg|qn|pay|rw|cn)_[0-9a-f]{8}\b")
TAGGED_RE = re.compile(r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)\s*(?:%|ms|MB|s|x|rows)?\s*\[(tc_[0-9a-f]{8})\]")
NUMBER_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _leaves(obj) -> list[float]:
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [v for x in obj.values() for v in _leaves(x)]
    if isinstance(obj, list):
        return [v for x in obj for v in _leaves(x)]
    return []


def _matches(written: str, values: list[float]) -> bool:
    text = written.replace(",", "")
    decimals = len(text.split(".")[1]) if "." in text else 0
    target = float(text)
    return any(round(v, decimals) == target for v in values)


def check(text: str, results: dict[str, object]) -> tuple[bool, list[str], list[dict]]:
    """(ok, unmatched numbers as written, [{value, tool_call_id}] for matched ones)."""
    # Blank out every code except the tool-call tags, so code digits are never read as numbers.
    body = CODE_RE.sub(lambda m: m.group(0) if m.group(0).startswith("tc_") else " ", text)
    matched, unmatched, tagged = [], [], []
    for m in TAGGED_RE.finditer(body):
        number, tc = m.group(1), m.group(2)
        tagged.append(number)
        if tc in results and _matches(number, _leaves(results[tc])):
            matched.append({"value": float(number.replace(",", "")), "tool_call_id": tc})
        else:
            unmatched.append(number)
    # Every number left after removing the tags must be one of the tagged numbers above.
    for m in NUMBER_RE.finditer(re.sub(r"\[tc_[0-9a-f]{8}\]", " ", body)):
        if m.group(0) in tagged:
            tagged.remove(m.group(0))
        else:
            unmatched.append(m.group(0))
    return (not unmatched), unmatched, matched


def strip_tags(text: str) -> str:
    return re.sub(r"\s*\[tc_[0-9a-f]{8}\]", "", text)
