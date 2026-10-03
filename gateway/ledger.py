"""Payload ledger: every payload bound for the AI side (or the local scanner) is scanned and
written here as a LedgerEntry, one JSON line each, before it leaves."""
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
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def record(self, destination: str, body: bytes, hits: list[dict]) -> dict:
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
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
