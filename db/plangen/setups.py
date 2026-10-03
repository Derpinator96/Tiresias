"""Index setups for plan generation (doc, "Data and training plan": 4 to 5 index setups per
query). Each setup is a database-wide set of indexes on top of the primary keys. The runner
drops every non-primary, non-unique index before applying the next setup, so setups never
mix. Setup IDs follow decision H: `s_` plus a lowercase slug.

These are workload definitions, not tunables: the counts they must meet come from
config.yaml (plan_generation.index_setups_per_query_min and _max).
"""
from __future__ import annotations

import re

import numpy as np

QUICKMART = {
    "s_qm_base": [],
    "s_qm_fk": [
        "CREATE INDEX ON sales (customer_id)", "CREATE INDEX ON sales (product_id)",
        "CREATE INDEX ON sales (store_id)", "CREATE INDEX ON sales (region_id)",
        "CREATE INDEX ON returns (order_id)",
    ],
    "s_qm_dates": [
        "CREATE INDEX ON sales (transaction_date)", "CREATE INDEX ON returns (return_date)",
        "CREATE INDEX ON customers (signup_date)",
    ],
    "s_qm_region_date": ["CREATE INDEX ON sales (region_id, transaction_date)"],
    "s_qm_mixed": [
        "CREATE INDEX ON sales (store_id, transaction_date)", "CREATE INDEX ON customers (segment)",
        "CREATE INDEX ON products (category)", "CREATE INDEX ON sales (customer_id)",
    ],
}

_TPCH_FK = [
    "CREATE INDEX ON lineitem (l_partkey)", "CREATE INDEX ON lineitem (l_suppkey)",
    "CREATE INDEX ON orders (o_custkey)", "CREATE INDEX ON partsupp (ps_suppkey)",
    "CREATE INDEX ON customer (c_nationkey)", "CREATE INDEX ON supplier (s_nationkey)",
    "CREATE INDEX ON nation (n_regionkey)",
]
_TPCH_DATES = [
    "CREATE INDEX ON lineitem (l_shipdate)", "CREATE INDEX ON orders (o_orderdate)",
    "CREATE INDEX ON lineitem (l_receiptdate)", "CREATE INDEX ON lineitem (l_commitdate)",
]
TPCH = {
    "s_tpch_base": [],
    "s_tpch_fk": _TPCH_FK,
    "s_tpch_dates": _TPCH_DATES,
    "s_tpch_fk_dates": _TPCH_FK + _TPCH_DATES,
    "s_tpch_composite": [
        "CREATE INDEX ON lineitem (l_shipdate, l_discount, l_quantity)",
        "CREATE INDEX ON orders (o_orderdate, o_custkey)", "CREATE INDEX ON lineitem (l_partkey, l_suppkey)",
        "CREATE INDEX ON part (p_type)", "CREATE INDEX ON part (p_brand, p_container)",
    ],
}

# TPC-H primary keys from the TPC-H specification. tpch-kit's dss.ddl declares none, and its
# dss.ri is not checked against Postgres, so these are added by the loader instead.
TPCH_PRIMARY_KEYS = [
    "ALTER TABLE region ADD PRIMARY KEY (r_regionkey)",
    "ALTER TABLE nation ADD PRIMARY KEY (n_nationkey)",
    "ALTER TABLE part ADD PRIMARY KEY (p_partkey)",
    "ALTER TABLE supplier ADD PRIMARY KEY (s_suppkey)",
    "ALTER TABLE partsupp ADD PRIMARY KEY (ps_partkey, ps_suppkey)",
    "ALTER TABLE customer ADD PRIMARY KEY (c_custkey)",
    "ALTER TABLE orders ADD PRIMARY KEY (o_orderkey)",
    "ALTER TABLE lineitem ADD PRIMARY KEY (l_orderkey, l_linenumber)",
]


def create_index_statements(sql_text: str) -> list[str]:
    """CREATE INDEX statements from a SQL file, comments removed."""
    no_comments = re.sub(r"--[^\n]*", "", sql_text)
    return [s.strip() for s in no_comments.split(";") if re.match(r"\s*create\s+index", s, re.I)]


def dsb_setups(index_sql_text: str, seed: int) -> dict[str, list[str]]:
    """DSB's own Postgres index file (scripts/dsb_index_pg.sql) gives the full setup; two
    seeded halves and the date-key subset give three more."""
    full = create_index_statements(index_sql_text)
    order = np.random.default_rng(seed).permutation(len(full))
    half = len(full) // 2
    return {
        "s_dsb_base": [],
        "s_dsb_all": full,
        "s_dsb_half_a": [full[i] for i in sorted(order[:half])],
        "s_dsb_half_b": [full[i] for i in sorted(order[half:])],
        "s_dsb_dates": [s for s in full if "date_sk" in s.lower()],
    }
