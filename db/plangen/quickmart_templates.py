"""QuickMart query templates for plan generation, with parameter samplers.

Parameters come from the generator's own domains (region IDs, date range, categories,
segments, cities), never from canary values. Q1 to Q4 are the doc's demo queries; they are
flagged `demo` so GNN training can hold them out and report on them honestly. Q3 and Q4 are
written from the doc's one-line descriptions; the doc gives no SQL for them.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from common.config import cfg
from db import generate


def _day(rng, lo: date, hi: date) -> date:
    return lo + timedelta(days=int(rng.integers(0, (hi - lo).days + 1)))


def _ctx():
    return {
        "d0": date.fromisoformat(cfg("dataset.date_start")),
        "d1": date.fromisoformat(cfg("dataset.date_end")),
        "regions": int(cfg("dataset.regions_rows")),
        "stores": int(cfg("dataset.stores_rows")),
        "customers": generate.sizes(int(cfg("plan_generation.quickmart_sales_rows")))["customers"],
        "price": cfg("dataset.unit_price_range"),
        "qty": cfg("dataset.quantity_range"),
    }


def _month(rng, c) -> date:
    d = _day(rng, c["d0"], c["d1"])
    return d.replace(day=1)


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


# (template_id, demo, SQL with {name} placeholders filled by quoted literals, sampler)
TEMPLATES = [
    ("qm/q1", True,
     "SELECT SUM(amount) FROM sales WHERE region_id = {r} AND transaction_date >= {d}",
     lambda rng, c: {"r": rng.integers(1, c["regions"] + 1), "d": _day(rng, c["d0"], c["d1"])}),
    ("qm/q2", True,
     "SELECT p.category, SUM(s.amount) FROM sales s JOIN products p ON p.product_id = s.product_id "
     "JOIN stores st ON st.store_id = s.store_id WHERE st.region_id = {r} "
     "AND date_trunc('month', s.transaction_date) = {m} GROUP BY p.category",
     lambda rng, c: {"r": rng.integers(1, c["regions"] + 1), "m": _month(rng, c)}),
    ("qm/q2_rewritten", True,
     "SELECT p.category, SUM(s.amount) FROM sales s JOIN products p ON p.product_id = s.product_id "
     "JOIN stores st ON st.store_id = s.store_id WHERE st.region_id = {r} "
     "AND s.transaction_date >= {m} AND s.transaction_date < {m2} GROUP BY p.category",
     lambda rng, c: (lambda m: {"r": rng.integers(1, c["regions"] + 1), "m": m, "m2": _next_month(m)})(_month(rng, c))),
    ("qm/q3_month_report", True,
     "SELECT store_id, COUNT(*), SUM(amount) FROM sales WHERE transaction_date >= {m} "
     "AND transaction_date < {m2} GROUP BY store_id",
     lambda rng, c: (lambda m: {"m": m, "m2": _next_month(m)})(_month(rng, c))),
    ("qm/q4_segment_date", True,
     "SELECT c.segment, s.transaction_date, SUM(s.amount) FROM sales s "
     "JOIN customers c ON c.customer_id = s.customer_id WHERE c.segment = {seg} "
     "AND s.transaction_date BETWEEN {d} AND {d2} GROUP BY c.segment, s.transaction_date",
     lambda rng, c: (lambda d: {"seg": rng.choice(generate.SEGMENTS), "d": d,
                                "d2": d + timedelta(days=int(rng.integers(1, 60)))})(_day(rng, c["d0"], c["d1"]))),
    ("qm/store_city_top", False,
     "SELECT st.city, SUM(s.amount) FROM sales s JOIN stores st ON st.store_id = s.store_id "
     "WHERE s.region_id = {r} GROUP BY st.city ORDER BY 2 DESC LIMIT 10",
     lambda rng, c: {"r": rng.integers(1, c["regions"] + 1)}),
    ("qm/brand_by_category", False,
     "SELECT p.brand, COUNT(*) FROM sales s JOIN products p ON p.product_id = s.product_id "
     "WHERE p.category = {cat} AND s.quantity >= {q} GROUP BY p.brand",
     lambda rng, c: {"cat": rng.choice(generate.CATEGORIES), "q": rng.integers(c["qty"][0], c["qty"][1] + 1)}),
    ("qm/returns_by_reason", False,
     "SELECT r.reason, COUNT(*), AVG(r.return_date - s.transaction_date) FROM returns r "
     "JOIN sales s ON s.order_id = r.order_id WHERE s.region_id = {r} AND r.return_date >= {d} GROUP BY r.reason",
     lambda rng, c: {"r": rng.integers(1, c["regions"] + 1), "d": _day(rng, c["d0"], c["d1"])}),
    ("qm/customer_recent_orders", False,
     "SELECT order_id, amount FROM sales WHERE customer_id = {cid} ORDER BY transaction_date DESC LIMIT 20",
     lambda rng, c: {"cid": rng.integers(1, c["customers"] + 1)}),
    ("qm/store_payment_mix", False,
     "SELECT payment_method, SUM(amount) FROM sales WHERE store_id = {sid} AND transaction_date >= {d} "
     "GROUP BY payment_method",
     lambda rng, c: {"sid": rng.integers(1, c["stores"] + 1), "d": _day(rng, c["d0"], c["d1"])}),
    ("qm/city_signups", False,
     "SELECT COUNT(*) FROM customers WHERE city = {city} AND signup_date >= {d}",
     lambda rng, c: {"city": rng.choice(generate.CITIES), "d": _day(rng, c["d0"], c["d1"])}),
    ("qm/large_orders", False,
     "SELECT s.order_id, p.category, s.amount FROM sales s JOIN products p ON p.product_id = s.product_id "
     "WHERE s.amount > {amt} AND s.transaction_date >= {d} ORDER BY s.amount DESC LIMIT 50",
     lambda rng, c: {"amt": round(float(rng.uniform(c["price"][0], c["price"][1] * c["qty"][1])), 2),
                     "d": _day(rng, c["d0"], c["d1"])}),
    ("qm/region_daily", False,
     "SELECT transaction_date, SUM(amount) FROM sales WHERE region_id IN ({r}, {r2}) "
     "AND transaction_date BETWEEN {d} AND {d2} GROUP BY transaction_date",
     lambda rng, c: (lambda d: {"r": rng.integers(1, c["regions"] + 1), "r2": rng.integers(1, c["regions"] + 1),
                                "d": d, "d2": d + timedelta(days=int(rng.integers(7, 120)))})(_day(rng, c["d0"], c["d1"]))),
    ("qm/customer_segment_spend", False,
     "SELECT c.city, COUNT(DISTINCT s.customer_id), SUM(s.amount) FROM customers c "
     "JOIN sales s ON s.customer_id = c.customer_id WHERE c.segment = {seg} AND c.signup_date >= {d} GROUP BY c.city",
     lambda rng, c: {"seg": rng.choice(generate.SEGMENTS), "d": _day(rng, c["d1"] - timedelta(days=90), c["d1"])}),
]


def literal(v) -> str:
    """A SQL literal for a generated parameter (numbers, dates, short ASCII strings only)."""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    s = str(v)
    assert "'" not in s, s
    return f"'{s}'"


def instances(n_sets: int, seed: int) -> list[tuple[str, bool, list[str]]]:
    c = _ctx()
    out = []
    for i, (tid, demo, sql, sampler) in enumerate(TEMPLATES):
        rng = np.random.default_rng([seed, i])
        out.append((tid, demo, [sql.format(**{k: literal(v) for k, v in sampler(rng, c).items()}) for _ in range(n_sets)]))
    return out
