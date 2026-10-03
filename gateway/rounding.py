"""Round every count and size to N significant figures (N from config.yaml)."""
from __future__ import annotations

import math

from common.config import cfg


def round_sig(x: float, digits: int | None = None) -> float:
    digits = int(cfg("gateway.round_significant_figures")) if digits is None else digits
    if x == 0 or not math.isfinite(x):
        return 0.0 if x == 0 else x
    return round(x, -int(math.floor(math.log10(abs(x)))) + (digits - 1))


def round_count(x: float) -> int:
    return int(round_sig(float(x)))


def round_ms(ms: float) -> float:
    """Timings are not counts or sizes; they keep microsecond resolution."""
    return round(float(ms), 3)
