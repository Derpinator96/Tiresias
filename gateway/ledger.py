"""Payload ledger: every payload bound for the AI side (or the local scanner) is scanned and
written here as a LedgerEntry, one JSON line each, before it leaves.

The bytes of every allowed payload to the AI side or the LLM are kept too, in a sibling file
(ledger_bodies.jsonl next to ledger.jsonl), keyed by payload_id: the doc's "record of every
byte the AI received", and the input of the adversarial leak test. Blocked payloads and the
negative control's raw text are never kept, so the file holds hashed data only."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timezone

from contracts.validate import validate


class Ledger:
    def __init__(self, path: str):
        self.path = path
        self.bodies_path = os.path.splitext(path)[0] + "_bodies.jsonl"
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def record(self, destination: str, body: bytes, hits: list[dict], keep_body: bool = True) -> dict:
        entry = {
            "payload_id": "pay_" + secrets.token_hex(4),
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "destination": destination,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "canary_hits": hits,
            "verdict": "block" if hits else "allow",
        }
        validate("LedgerEntry", entry)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            if keep_body and entry["verdict"] == "allow" and destination in ("ai", "llm"):
                with open(self.bodies_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"payload_id": entry["payload_id"], "body": body.decode("utf-8")}) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def payloads(self, since: datetime, until: datetime) -> list[dict]:
        """Kept bodies whose entry time is in [since, until], oldest first, one copy per sha256."""
        if not os.path.exists(self.bodies_path):
            return []
        # ponytail: reads the whole bodies file per call; index by time if it grows past memory.
        with open(self.bodies_path, encoding="utf-8") as f:
            bodies = {d["payload_id"]: d["body"] for d in (json.loads(line) for line in f if line.strip())}
        out, seen = [], set()
        for e in self.entries():
            t = datetime.fromisoformat(e["time"].replace("Z", "+00:00"))
            if e["payload_id"] in bodies and since <= t <= until and e["sha256"] not in seen:
                seen.add(e["sha256"])
                out.append({"payload_id": e["payload_id"], "time": e["time"], "destination": e["destination"],
                            "body": bodies[e["payload_id"]]})
        return out
