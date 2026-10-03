"""Stand-in for Ollama, for proving the air-gapped path without the real model. Stdlib only, so
it runs on the host's own Python: python3 infra/tests/fake_ollama.py 10.31.31.1 11434

It answers GET /api/version (as "standin", so a test can tell it from a real Ollama),
GET /api/tags and POST /api/chat, where it plays a fixed Q1 tool sequence and then answers
with two numbers copied from the simulate result, tagged with that call's ID. It prints the
size of every request, which is how the real Q1 prompt sizes were measured (agent/NOTES.md).
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL = "gemma2:2b"
SEQUENCE = ["get_slow_templates", "get_plan", "mine_candidates", "run_rl", "simulate"]
RESULT = re.compile(r"Result of (tc_[0-9a-f]{8}) \((\w+)\): (.*)", re.S)


def reply(messages: list[dict]) -> dict:
    results = [RESULT.match(m["content"]) for m in messages if m["role"] == "user"]
    results = [r for r in results if r]
    tid = re.search(r"templates: (q_[0-9a-f]{8})", messages[1]["content"]).group(1)
    if len(results) < len(SEQUENCE):
        name, args = SEQUENCE[len(results)], {}
        if name == "get_plan":
            args = {"template_id": tid}
        if name == "simulate":
            args = {"config_id": json.loads(results[-1].group(3))["config"]["config_id"]}
        return {"name": name, "args": args, "answer": ""}
    tc0, slow = results[0].group(1), json.loads(results[0].group(3))
    mean = next(t["mean_ms"] for t in slow if t["template_id"] == tid)
    text = f"Template {tid} averages {mean} ms [{tc0}] per call."
    tc, sim = results[-1].group(1), json.loads(results[-1].group(3))
    if sim.get("templates"):     # simulate fails when the search recommends no index
        t = sim["templates"][0]
        text += f" Measured on the twin: {t['before_ms']} ms [{tc}] before the index and {t['after_ms']} ms [{tc}] after."
    return {"name": "final_answer", "args": {}, "answer": text}


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/version":
            return self.send(200, {"version": "standin"})
        if self.path == "/api/tags":
            return self.send(200, {"models": [{"name": MODEL, "model": MODEL}]})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        body = json.loads(raw)
        if self.path != "/api/chat" or body.get("stream") is not False or "format" not in body:
            return self.send(400, {"error": "standin expects a non-streaming /api/chat request with format"})
        chars = sum(len(m["content"]) for m in body["messages"])
        print(f"chat request: {len(raw)} bytes, {len(body['messages'])} messages, {chars} content characters, "
              f"num_ctx {body['options']['num_ctx']}", flush=True)
        self.send(200, {"model": body["model"], "message": {"role": "assistant", "content": json.dumps(reply(body["messages"]))},
                        "done": True, "done_reason": "stop", "prompt_eval_count": 0, "eval_count": 0})


if __name__ == "__main__":
    HTTPServer((sys.argv[1], int(sys.argv[2])), Handler).serve_forever()
