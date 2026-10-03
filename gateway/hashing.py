"""Keyed codes for every name that crosses the trust boundary (doc, Detailed component specs).

Code = prefix + the first N hex characters of HMAC-SHA256(key, name), N from config.yaml.
Tables hash "table"; columns hash "table.column", so two `id` columns in different tables
get different codes. Every code made is recorded in the vault (code -> real name), which
stays inside the gateway and is used only for dehashing answers for the DBA.
"""
from __future__ import annotations

import hashlib
import hmac
import threading

from common.config import cfg


class Hasher:
    def __init__(self, key: bytes):
        self._key = key
        self._n = int(cfg("gateway.hmac_code_hex_chars"))
        self._lock = threading.Lock()
        self.vault: dict[str, dict] = {}   # code -> {"kind": ..., "name": ...}

    def _code(self, prefix: str, text: str, kind: str, name: str) -> str:
        digest = hmac.new(self._key, text.encode("utf-8"), hashlib.sha256).hexdigest()[: self._n]
        code = f"{prefix}_{digest}"
        with self._lock:
            self.vault.setdefault(code, {"kind": kind, "name": name})
        return code

    def table(self, table: str) -> str:
        return self._code("t", table, "table", table)

    def column(self, table: str, column: str) -> str:
        return self._code("c", f"{table}.{column}", "column", f"{table}.{column}")

    def index(self, index_name: str) -> str:
        return self._code("i", f"index:{index_name}", "index", index_name)

    def template(self, normalized_sql: str) -> str:
        # Keyed on the normalized text, so the code is stable across reseeds (queryid is not:
        # it depends on table OIDs).
        return self._code("q", f"template:{normalized_sql}", "template", normalized_sql)

    def opaque(self, prefix: str, text: str) -> str:
        """Codes for IDs that name nothing real (plan IDs). Not recorded in the vault."""
        return f"{prefix}_" + hmac.new(self._key, text.encode("utf-8"), hashlib.sha256).hexdigest()[: self._n]
