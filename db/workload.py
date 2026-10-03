"""The real workload run against pg-prod (private side only).

Q1 is the hero query from the doc's "Demo queries". The four canary queries plant canaries
in query comments and filter values, so the gateway's stripping is exercised on real logs.
"""
from __future__ import annotations

from common.config import cfg
from db import canaries

Q1_TEMPLATE = "SELECT SUM(amount) FROM sales WHERE region_id = {region} AND transaction_date >= '{since}'"


def q1_sql() -> str:
    """Q1 exactly as the dashboard would send it, literals included."""
    return Q1_TEMPLATE.format(region=int(cfg("dataset.hero_region_id")), since=cfg("workload.q1_since"))


def canary_queries() -> list[str]:
    c1, c2 = canaries.COMMENTS
    email, name = canaries.FILTERS
    return [
        f"/* {c1.value} */ SELECT COUNT(*) FROM customers WHERE segment = 'retail'",
        f"SELECT COUNT(*) FROM products WHERE category = 'kitchen' -- {c2.value}",
        f"SELECT customer_id FROM customers WHERE email = '{email.value}'",
        f"SELECT customer_id FROM customers WHERE full_name = '{name.value}'",
    ]
