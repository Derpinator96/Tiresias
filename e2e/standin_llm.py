"""Scripted stand-in model for e2e/test_invented_number.py. No LLM is called.

Reuses infra/tests/fake_ollama.py's Ollama stand-in server (stdlib only, runs on the host's own
Python); only the reply changes: one get_slow_templates call, then an answer with one number
copied from that result and one planted number that is in no tool result, both tagged with the
call's ID. It gives the same answer after the checker's feedback, so every retry is rejected.

    python3 -m e2e.standin_llm 10.31.31.1 11434      # llm.ollama.base_url's address
"""
import json
import sys
from http.server import HTTPServer

from infra.tests import fake_ollama

PLANTED = "31337.271828"     # six decimals: no tool result value rounds to it


def reply(messages: list[dict]) -> dict:
    results = [r for r in (fake_ollama.RESULT.match(m["content"]) for m in messages if m["role"] == "user") if r]
    if not results:
        return {"name": "get_slow_templates", "args": {}, "answer": ""}
    tc, slow = results[0].group(1), json.loads(results[0].group(3))
    t = slow[0]
    return {"name": "final_answer", "args": {},
            "answer": f"Template {t['template_id']} averages {t['mean_ms']} ms [{tc}]; an index would save {PLANTED} ms [{tc}]."}


if __name__ == "__main__":
    fake_ollama.reply = reply          # Handler.do_POST looks reply up in its own module
    HTTPServer((sys.argv[1], int(sys.argv[2])), fake_ollama.Handler).serve_forever()
