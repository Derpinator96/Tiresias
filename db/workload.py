"""The real workload run against pg-prod (private side only).

Q1 is the hero query, Q2 the join query and Q4 the drift query from the doc's "Demo queries".
The four canary queries plant canaries in query comments and filter values, so the gateway's
stripping is exercised on real logs.
"""
from __future__ import annotations

from common.config import cfg
from db import canaries

Q1_TEMPLATE = "SELECT SUM(amount) FROM sales WHERE region_id = {region} AND transaction_date >= '{since}'"


def q1_sql() -> str:
    """Q1 exactly as the dashboard would send it, literals included."""
    return Q1_TEMPLATE.format(region=int(cfg("dataset.hero_region_id")), since=cfg("workload.q1_since"))


# Q2 (doc): needs a rewrite plus an index. date_trunc on the date column stops Postgres from
# using any index on it; the expected rewrite is a half-open range on the bare column.
Q2_TEMPLATE = ("SELECT p.category, SUM(s.amount) FROM sales s "
               "JOIN products p ON p.product_id = s.product_id "
               "JOIN stores st ON st.store_id = s.store_id "
               "WHERE st.region_id = {region} AND date_trunc('month', s.transaction_date) = '{month}' "
               "GROUP BY p.category")


def q2_sql() -> str:
    return Q2_TEMPLATE.format(region=int(cfg("dataset.hero_region_id")), month=cfg("workload.q2_month"))


# Not in the doc: added for the rewrite demo (human decision 2026-10-03). VeriEQL cannot encode
# date_trunc, so Q2's rewrite can only be TestedOnly; this two-region report has the
# `col = a OR col = b` shape that VeriEQL can verify, so one rewrite is truly Verified.
QOR_TEMPLATE = ("SELECT SUM(amount) FROM sales WHERE (region_id = {a} OR region_id = {b}) "
                "AND transaction_date >= '{since}'")


def qor_sql() -> str:
    a, b = cfg("workload.qor_regions")
    return QOR_TEMPLATE.format(a=int(a), b=int(b), since=cfg("workload.q1_since"))


# Q4 (doc): "a new report on customer segment plus date, introduced mid-demo so the RL agent must
# adapt". The doc gives no SQL; same shape as plan generation's qm/q4_segment_date. It runs only
# in `make drift-demo` (db/drift_demo.py), never in the default `make seed` workload.
Q4_TEMPLATE = ("SELECT c.segment, s.transaction_date, SUM(s.amount) FROM sales s "
               "JOIN customers c ON c.customer_id = s.customer_id "
               "WHERE c.segment = '{segment}' AND s.transaction_date BETWEEN '{start}' AND '{end}' "
               "GROUP BY c.segment, s.transaction_date")


def q4_sql() -> str:
    start, end = cfg("workload.q4_dates")
    return Q4_TEMPLATE.format(segment=cfg("workload.q4_segment"), start=start, end=end)


QUERIES = {"q1": q1_sql, "q2": q2_sql, "qor": qor_sql, "q4": q4_sql}


def canary_queries() -> list[str]:
    c1, c2 = canaries.COMMENTS
    email, name = canaries.FILTERS
    return [
        f"/* {c1.value} */ SELECT COUNT(*) FROM customers WHERE segment = 'retail'",
        f"SELECT COUNT(*) FROM products WHERE category = 'kitchen' -- {c2.value}",
        f"SELECT customer_id FROM customers WHERE email = '{email.value}'",
        f"SELECT customer_id FROM customers WHERE full_name = '{name.value}'",
    ]
