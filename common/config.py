"""Read config.yaml. Every tunable value comes from here, never from code.

    from common.config import cfg
    cfg("miner.max_index_columns")   # -> 3; raises KeyError if the key is missing

The file path defaults to config.yaml at the repo root; BT_CONFIG overrides it (used by tests).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return Path(os.environ.get("BT_CONFIG", REPO_ROOT / "config.yaml"))


@lru_cache(maxsize=None)
def load(path: str | None = None) -> dict[str, Any]:
    with open(path or config_path(), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must hold a mapping at the top level")
    return data


def cfg(dotted_key: str) -> Any:
    """Return one value by dotted path. A missing key is an error, never a silent default."""
    node: Any = load()
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"config.yaml has no key {dotted_key!r}")
        node = node[part]
    return node


def leaves(prefix: str = "", node: Any = None) -> dict[str, Any]:
    """Flatten the config into {"section.key": value}."""
    node = load() if node is None else node
    out: dict[str, Any] = {}
    for k, v in node.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(leaves(f"{key}.", v))
        else:
            out[key] = v
    return out
