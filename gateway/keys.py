"""The HMAC key. Read only from the BT_HMAC_KEY environment variable (filled from the
uncommitted .env). Never printed, logged or returned by any endpoint."""
from __future__ import annotations

import os

from common.config import cfg


class MissingKey(RuntimeError):
    pass


def hmac_key() -> bytes:
    raw = os.environ.get("BT_HMAC_KEY", "")
    if not raw:
        raise MissingKey("BT_HMAC_KEY is not set; the gateway refuses to hash without it (fail closed)")
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        raise MissingKey("BT_HMAC_KEY is not hex") from None
    if len(key) != int(cfg("gateway.hmac_key_bytes")):
        raise MissingKey("BT_HMAC_KEY has the wrong length")
    return key
