"""Canary scanner (doc, Privacy tests): case-insensitive search for every canary and for
any N-character fragment of one (N from config.yaml), on every payload."""
from __future__ import annotations

from common.config import cfg
from db import canaries as canary_list


class Scanner:
    def __init__(self, items=None, fragment_chars: int | None = None):
        self.items = list(canary_list.ALL if items is None else items)
        k = int(cfg("gateway.canary_fragment_chars")) if fragment_chars is None else fragment_chars
        self._exact = [(c.canary_id, c.value.lower()) for c in self.items]
        self._frags = [(c.canary_id, {v[i:i + k] for i in range(max(1, len(v) - k + 1))})
                       for c, (_, v) in zip(self.items, self._exact)]

    def scan(self, text: str) -> list[dict]:
        """Hits as contract-shaped {canary_id, match}; never the canary value itself."""
        low = text.lower()
        hits = []
        for (cid, value), (_, frags) in zip(self._exact, self._frags):
            if value in low:
                hits.append({"canary_id": cid, "match": "exact"})
            elif any(f in low for f in frags):
                hits.append({"canary_id": cid, "match": "fragment"})
        return hits
