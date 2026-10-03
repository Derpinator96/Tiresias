"""Export raw plans as the GNN training dataset (private side, bench container).

Each plan goes through the gateway's own hash_plan() (same rounding and self_ms as serving),
then models.gnn.features.strip(). The hashing key is random per export and never saved; the
stripped nodes hold no codes anyway. Template IDs become opaque group keys; setup IDs become
their position in the database's setup list. Output may leave the machine (Colab), so
db/plangen/tests/test_export.py checks that every string in it is on an allow-list.

    python -m db.plangen export   -> data/gnn/dataset.jsonl.gz and data/gnn/split.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import secrets
from pathlib import Path

import numpy as np
import psycopg

from common.config import REPO_ROOT, cfg
from db.plangen import load, setups
from gateway import catalog
from gateway.hashing import Hasher
from gateway.ingest.plans import hash_plan
from models.gnn import features


def group_key(database: str, template_id: str) -> str:
    """Keyed by benchmark family, so one template at two QuickMart scales is one group and can
    never sit in both train and test."""
    return "g_" + hashlib.sha1(f"{load.family(database)}|{template_id}".encode()).hexdigest()[:12]


def setup_orders() -> dict[str, list[str]]:
    """Setup IDs in their fixed order per database, so a setup exports as its index."""
    return {"quickmart": list(setups.QUICKMART), "tpch": list(setups.TPCH),
            "dsb": list(setups.dsb_setups("", 0))}   # keys do not depend on the index file


def export_record(rec: dict, hasher: Hasher, schema: dict[str, set[str]], order: list[str]) -> dict:
    hp = hash_plan(rec["plan"], plan_id="p_00000000", template_id="q_00000000", setup_id=rec["setup_id"],
                   source="explain", hasher=hasher, schema=schema)
    return {"group": group_key(rec["database"], rec["template_id"]), "database": load.family(rec["database"]),
            "demo": rec["demo"], "setup": order.index(rec["setup_id"]), "param_set": rec["param_set"],
            "timed_out": rec["timed_out"], "total_ms": rec["runtime_ms"],
            "nodes": [features.strip(n) for n in hp["nodes"]]}


def make_split(groups: dict[str, bool], seed: int) -> dict:
    """groups: {group: demo}. Template-level split from gnn.template_split; demo groups
    (Q1 to Q4 and the Q2 rewrite) always go to test so their results are honest."""
    tr, va, _ = cfg("gnn.template_split")
    rest = sorted(g for g, demo in groups.items() if not demo)
    rest = [rest[i] for i in np.random.default_rng(seed).permutation(len(rest))]
    a, b = round(len(rest) * tr), round(len(rest) * (tr + va))
    return {"seed": seed, "feature_version": features.FEATURE_VERSION, "train": sorted(rest[:a]),
            "val": sorted(rest[a:b]), "test": sorted(rest[b:] + [g for g, d in groups.items() if d])}


def export(raw: Path, out_dir: Path, log=print) -> dict:
    hasher = Hasher(secrets.token_bytes(int(cfg("gateway.hmac_key_bytes"))))
    schemas = {}
    for db in load.DATABASES:
        with psycopg.connect(load.dsn_for(db)) as conn:
            schemas[db] = catalog.read(conn).schema()
    orders = setup_orders()
    out_dir.mkdir(parents=True, exist_ok=True)
    groups: dict[str, bool] = {}
    n = 0
    with open(raw, encoding="utf-8") as f, gzip.open(out_dir / "dataset.jsonl.gz", "wt", encoding="utf-8") as out:
        for line in f:
            rec = json.loads(line)
            if rec["error"]:
                continue
            row = export_record(rec, hasher, schemas[rec["database"]], orders[load.family(rec["database"])])
            groups[row["group"]] = row["demo"]
            out.write(json.dumps(row) + "\n")
            n += 1
    split = make_split(groups, int(cfg("dataset.random_seed")))
    (out_dir / "split.json").write_text(json.dumps(split, indent=1))
    summary = {"plans": n, "groups": len(groups), **{k: len(split[k]) for k in ("train", "val", "test")}}
    log(json.dumps(summary))
    return summary


def default_paths(source: str) -> tuple[Path, Path]:
    plans = REPO_ROOT / cfg("plan_generation.output_dir")
    return plans / source, REPO_ROOT / cfg("gnn.dataset_dir")
