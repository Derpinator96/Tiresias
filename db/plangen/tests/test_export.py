"""Export checks that need no database. The export may leave the machine, so the privacy
test is an allow-list: every string in an exported record must be an operator name, a
database label or an opaque group key."""
import json
import re

import numpy as np

from db import canaries
from db.plangen import export
from gateway.hashing import Hasher
from gateway.ingest.plans import hash_plan
from models.gnn import features

SCHEMA = {"sales": {"order_id", "region_id", "transaction_date", "amount", "store_id"},
          "stores": {"store_id", "region_id", "city"}}
PLAN = {"Plan": {"Node Type": "Aggregate", "Plan Rows": 1, "Total Cost": 18234.5, "Plan Width": 32,
                 "Actual Total Time": 30.0, "Actual Loops": 1, "Actual Rows": 1, "Plans": [
    {"Node Type": "Hash Join", "Plan Rows": 2407, "Total Cost": 18000.1, "Plan Width": 6,
     "Hash Cond": "(s.store_id = st.store_id)", "Actual Total Time": 29.0, "Actual Loops": 1, "Actual Rows": 2400,
     "Plans": [
        {"Node Type": "Seq Scan", "Relation Name": "sales", "Alias": "s", "Plan Rows": 2407, "Total Cost": 17000.0,
         "Plan Width": 10, "Filter": "((region_id = 7) AND (transaction_date >= '2026-09-26'::date) AND (amount <> 7731.77))",
         "Actual Total Time": 25.0, "Actual Loops": 1, "Actual Rows": 2400, "Rows Removed by Filter": 997600},
        {"Node Type": "Index Scan", "Relation Name": "stores", "Alias": "st", "Index Name": "stores_pkey",
         "Plan Rows": 500, "Total Cost": 20.0, "Plan Width": 4, "Index Cond": "(city = 'Raipur')",
         "Actual Total Time": 1.0, "Actual Loops": 1, "Actual Rows": 500}]}]}}
RAW = {"plan_uid": "x", "database": "quickmart", "template_id": "qm/customer_recent_orders", "demo": False,
       "param_set": 3, "setup_id": "s_qm_region_date", "timed_out": False, "runtime_ms": 30.5,
       "plan": PLAN, "error": None}
ORDER = export.setup_orders()["quickmart"]


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def test_export_record_holds_only_allowed_strings():
    row = export.export_record(RAW, Hasher(b"k" * 32), SCHEMA, ORDER)
    keys = {"group", "database", "demo", "setup", "param_set", "timed_out", "total_ms", "nodes", "op", "parent",
            "est_rows", "est_cost", "width", "has_index", "n_filter_cols", "filter_redacted", "self_ms", "actual_rows"}
    for s in strings(row):
        assert s in keys or s in features.OPS or s in ("quickmart", "tpch", "dsb") or re.fullmatch(r"g_[0-9a-f]{12}", s), s
    text = json.dumps(row)
    assert not any(c.value in text for c in canaries.ALL)
    assert not re.search(r"\b[tcipq]_[0-9a-f]{8}\b", text)
    assert row["setup"] == ORDER.index("s_qm_region_date") and row["nodes"][2]["n_filter_cols"] >= 2


def test_features_match_serving_path():
    # Serving: the gateway's HashedPlan (production key) -> strip -> features.
    # Training: the export (throwaway key) -> features. Keys differ; features must not.
    served = hash_plan(PLAN, plan_id="p_00000001", template_id="q_00000001", setup_id="s_baseline",
                       source="auto_explain", hasher=Hasher(b"prod" * 8), schema=SCHEMA)
    a = features.node_features([features.strip(n) for n in served["nodes"]])
    b = features.node_features(export.export_record(RAW, Hasher(b"other" * 7), SCHEMA, ORDER)["nodes"])
    assert np.array_equal(a, b)


def test_features_and_targets_shapes():
    nodes = export.export_record(RAW, Hasher(b"k" * 32), SCHEMA, ORDER)["nodes"]
    x, y = features.node_features(nodes), features.targets(nodes)
    assert x.shape == (4, features.N_FEATURES) and y.shape == (4,)
    assert features.parents(nodes).tolist() == [-1, 0, 1, 1]
    # Costs arrive rounded to 2 significant figures: hash join 18000, children 17000 + 20.
    assert np.isclose(np.expm1(x[1, len(features.OPS) + 2]), 18000 - 17020)
    assert np.isclose(np.expm1(y[2]), 25.0)                 # leaf seq scan: self_ms = its total
    assert np.isclose(np.expm1(y[1]), 29.0 - 25.0 - 1.0)    # hash join: total minus children
    assert features.plan_features(nodes).shape == (len(features.OPS) + 2 * len(features.NUMERIC),)


def test_split_by_group_with_demo_in_test():
    groups = {f"g_{i:012x}": False for i in range(40)} | {"g_demo00000001": True}
    s = export.make_split(groups, 7)
    parts = [set(s[k]) for k in ("train", "val", "test")]
    assert sum(map(len, parts)) == 41 and not (parts[0] & parts[1] or parts[0] & parts[2] or parts[1] & parts[2])
    assert "g_demo00000001" in parts[2] and len(parts[0]) == 28
    assert export.make_split(groups, 7) == s
