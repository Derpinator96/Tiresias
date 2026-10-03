"""The LLM agent loop: tool calls, then an answer that must pass the number checker.

Caps: at most llm.max_tool_calls tool calls; after that the model is told the cap is reached.
Checker: an answer with an unmatched number gets llm.checker_retries retries with feedback;
if it still fails, it is blocked and never shown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent import number_checker, prompts
from agent.tools import DECLARATIONS, Toolbox
from common.config import cfg
from contracts.validate import validate


@dataclass
class AgentResult:
    status: str                       # "ok" or "blocked_by_checker"
    answer: dict | None               # contract Answer when ok
    unmatched: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


def _text(content: dict) -> str:
    return "".join(p.get("text", "") for p in content.get("parts", []) if not p.get("thought"))


def ask(question_id: str, template_ids: list[str], llm, toolbox: Toolbox | None = None,
        on_event: Callable[[str], None] | None = None) -> AgentResult:
    toolbox = toolbox or Toolbox()
    events: list[str] = []

    def note(msg: str) -> None:
        events.append(msg)
        if on_event:
            on_event(msg)

    max_calls = int(cfg("llm.max_tool_calls"))
    system = prompts.system_prompt(max_calls)
    contents = [{"role": "user", "parts": [{"text": prompts.user_turn(question_id, template_ids)}]}]
    used = 0
    text = ""
    retries = int(cfg("llm.checker_retries"))
    while True:
        resp = llm.generate(system, contents, DECLARATIONS, on_event=note)
        content = resp["candidates"][0]["content"]
        contents.append(content)                     # sent back unchanged (thought signatures)
        calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
        if calls:
            parts = []
            for call in calls:
                if used >= max_calls:
                    tc, result = "tc_limit", {"error": f"tool call limit of {max_calls} reached; answer with the evidence you have"}
                else:
                    tc, result = toolbox.call(call["name"], call.get("args", {}))
                    used += 1
                    note(f"tool {call['name']} -> {tc}")
                fr = {"name": call["name"], "response": {"tool_call_id": tc, "result": result}}
                if call.get("id"):
                    fr["id"] = call["id"]
                parts.append({"functionResponse": fr})
            contents.append({"role": "user", "parts": parts})
            continue
        text = _text(content)
        ok, unmatched, numbers = number_checker.check(text, toolbox.results)
        if ok:
            answer = {"question_id": question_id, "text": number_checker.strip_tags(text).strip(), "numbers": numbers}
            validate("Answer", answer)
            return AgentResult("ok", answer, [], toolbox.calls, events)
        note(f"number checker rejected: {', '.join(unmatched)}")
        if retries <= 0:
            return AgentResult("blocked_by_checker", None, unmatched, toolbox.calls, events)
        retries -= 1
        contents.append({"role": "user", "parts": [{"text": prompts.checker_feedback(unmatched)}]})
