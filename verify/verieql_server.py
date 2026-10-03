"""VeriEQL as a private-network service (runs in the blind-tuner-verieql image; our code, MIT;
VeriEQL itself is CC BY-NC-SA 4.0 and lives only in that image, at $VERIEQL_HOME).

POST /check {"sql1", "sql2", "schema": {TABLE: {COL: TYPE}}, "constraints": [...],
             "bound": rows per table, "timeout_s": seconds}
  -> {"result": "pass" | "fail" | "unsupported", "detail": str, "seconds": float}

"pass" = equivalent for every database up to `bound` rows per table (bounded model checking,
not a proof for all sizes). "fail" = VeriEQL found a counterexample. "unsupported" = VeriEQL
could not encode the SQL or ran past the timeout. Each check runs in a child process that is
killed at the timeout. Standard library only, so nothing is added to VeriEQL's image.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8300


def _check(req: dict, out: mp.Queue) -> None:
    sys.path.insert(0, os.environ.get("VERIEQL_HOME", "/opt/verieql"))
    try:
        from constants import DIALECT
        from environment import Environment
        with Environment(dialect=DIALECT.POSTGRESQL) as env:
            for name, cols in req["schema"].items():
                env.create_database(attributes=cols, bound_size=int(req["bound"]), name=name)
            env.add_constraints(req.get("constraints") or [])
            env.save_checkpoints()
            same = env.analyze(req["sql1"], req["sql2"])
        out.put({"result": "pass" if same is True else "fail", "detail": "" if same is True else "counterexample found"})
    except Exception as e:   # VeriEQL raises on SQL it cannot encode
        out.put({"result": "unsupported", "detail": f"{type(e).__name__}: {str(e)[:300]}"})


def check(req: dict) -> dict:
    t0 = time.perf_counter()
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=_check, args=(req, q))
    p.start()
    p.join(float(req["timeout_s"]))
    if p.is_alive():
        p.kill()
        p.join()
        res = {"result": "unsupported", "detail": f"timeout after {req['timeout_s']} s"}
    else:
        res = q.get() if not q.empty() else {"result": "unsupported", "detail": f"verifier exited with {p.exitcode}"}
    return {**res, "seconds": round(time.perf_counter() - t0, 2)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200 if self.path == "/healthz" else 404, {"ok": self.path == "/healthz"})

    def do_POST(self):
        if self.path != "/check":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._send(200, check(req))
        except (KeyError, ValueError) as e:
            self._send(400, {"error": f"{type(e).__name__}"})

    def log_message(self, *args):   # real SQL must not land in container logs
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
