"""Generate QuickMart and load it into pg-prod (architecture doc, "Data generation rules").

1. Parents before children: regions, stores, products, customers, then sales, then returns.
2. Skew: region 7 holds 30% of sales; 20% of products earn 80% of revenue; dates run
   2024-01-01 to 2026-09-30, denser in recent months.
3. Correlation: each sale carries its store's region_id; returns follow their sale by 1 to
   30 days.
4. Primary and foreign keys only (db/schema.sql).
5. COPY, then ANALYZE.

Every size, share and date comes from config.yaml. Row canaries from db/canaries.py are
written over a few generated rows.
"""
from __future__ import annotations

import io
import os
import time
from datetime import date

import numpy as np
import pandas as pd
import psycopg

from common.config import cfg
from db import canaries

SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "schema.sql")

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Isha", "Arjun", "Sara", "Vihaan", "Anaya",
         "Dev", "Tara", "Neel", "Riya", "Kiran", "Zoya"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Gupta", "Das", "Khan", "Patel", "Singh",
        "Menon", "Rao", "Bose", "Joshi"]
CITIES = ["Raipur", "Bhilai", "Nagpur", "Pune", "Indore", "Bhopal", "Jaipur", "Lucknow", "Patna",
          "Ranchi", "Kochi", "Mysuru", "Surat", "Vadodara", "Nashik", "Guwahati"]
SEGMENTS = ["retail", "loyalty", "business", "student"]
CATEGORIES = ["kitchen", "grocery", "electronics", "apparel", "home", "toys", "beauty", "sports"]
BRANDS = ["Arkwell", "Brindle", "Cobalt", "Dunmore", "Elstree", "Fenwick", "Galloway", "Hollins"]
PAYMENTS = ["card", "upi", "cash", "wallet"]
REASONS = ["damaged", "wrong item", "not needed", "late delivery", "quality"]
PHONE_MAX = 999_999_999   # nine-digit local part of a generated phone number


def sizes() -> dict[str, int]:
    sales = int(cfg("dataset.sales_rows"))
    return {
        "regions": int(cfg("dataset.regions_rows")),
        "stores": int(cfg("dataset.stores_rows")),
        "products": int(cfg("dataset.products_rows")),
        "customers": round(sales * float(cfg("dataset.customers_per_sale"))),
        "sales": sales,
        "returns": round(sales * float(cfg("dataset.returns_per_sale"))),
    }


def _day_weights(n_days: int) -> np.ndarray:
    """Linear weight from 1 at the first day to recent_density_ratio at the last."""
    w = np.linspace(1.0, float(cfg("dataset.recent_density_ratio")), n_days)
    return w / w.sum()


def build(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    n = sizes()
    hero = int(cfg("dataset.hero_region_id"))
    hero_share = float(cfg("dataset.hero_region_share"))
    d0, d1 = date.fromisoformat(cfg("dataset.date_start")), date.fromisoformat(cfg("dataset.date_end"))
    n_days = (d1 - d0).days + 1
    epoch0 = np.datetime64(d0)

    regions = pd.DataFrame({"region_id": np.arange(1, n["regions"] + 1)})
    regions["region_name"] = [f"Region {i}" for i in regions.region_id]
    assert hero in set(regions.region_id), "hero_region_id must be a generated region"

    # Stores spread round-robin over regions, so every region has stores.
    stores = pd.DataFrame({"store_id": np.arange(1, n["stores"] + 1)})
    stores["region_id"] = (stores.store_id - 1) % n["regions"] + 1
    stores["city"] = rng.choice(CITIES, n["stores"])
    o_lo, o_hi = cfg("dataset.store_opened_days_before_start")
    stores["opened_on"] = epoch0 - rng.integers(o_lo, o_hi + 1, n["stores"]).astype("timedelta64[D]")

    products = pd.DataFrame({"product_id": np.arange(1, n["products"] + 1)})
    products["name"] = [f"{BRANDS[i % len(BRANDS)]} item {i}" for i in products.product_id]
    products["category"] = rng.choice(CATEGORIES, n["products"])
    products["brand"] = rng.choice(BRANDS, n["products"])
    p_lo, p_hi = cfg("dataset.unit_price_range")
    products["unit_price"] = np.round(rng.uniform(p_lo, p_hi, n["products"]), 2)

    customers = pd.DataFrame({"customer_id": np.arange(1, n["customers"] + 1)})
    customers["email"] = [f"user{i}@example.com" for i in customers.customer_id]
    customers["full_name"] = [f"{a} {b}" for a, b in zip(rng.choice(FIRST, n["customers"]), rng.choice(LAST, n["customers"]))]
    customers["phone"] = [f"+91-9{x:09d}" for x in rng.integers(0, PHONE_MAX + 1, n["customers"])]
    customers["city"] = rng.choice(CITIES, n["customers"])
    customers["signup_date"] = epoch0 + rng.integers(0, n_days, n["customers"]).astype("timedelta64[D]")
    customers["segment"] = rng.choice(SEGMENTS, n["customers"])

    # Sales: pick the region first (hero region at hero_share, others uniform), then a store
    # in that region, so each sale carries its store's region_id.
    others = [r for r in regions.region_id if r != hero]
    is_hero = rng.random(n["sales"]) < hero_share
    region = np.where(is_hero, hero, rng.choice(others, n["sales"]))
    stores_by_region = {r: stores.store_id[stores.region_id == r].to_numpy() for r in regions.region_id}
    store = np.empty(n["sales"], dtype=np.int64)
    for r, ids in stores_by_region.items():
        mask = region == r
        store[mask] = rng.choice(ids, mask.sum())

    # Products: the top share of products (by id order after shuffling) gets
    # top_product_revenue_share of all sales, so it earns about that share of revenue.
    top_n = round(n["products"] * float(cfg("dataset.top_product_share")))
    order = rng.permutation(products.product_id.to_numpy())
    top, rest = order[:top_n], order[top_n:]
    from_top = rng.random(n["sales"]) < float(cfg("dataset.top_product_revenue_share"))
    product = np.where(from_top, rng.choice(top, n["sales"]), rng.choice(rest, n["sales"]))

    day = rng.choice(n_days, n["sales"], p=_day_weights(n_days))
    q_lo, q_hi = cfg("dataset.quantity_range")
    qty = rng.integers(q_lo, q_hi + 1, n["sales"])
    price = products.set_index("product_id").unit_price.to_numpy()[product - 1]
    sales = pd.DataFrame({
        "order_id": np.arange(1, n["sales"] + 1),
        "customer_id": rng.integers(1, n["customers"] + 1, n["sales"]),
        "product_id": product,
        "store_id": store,
        "region_id": region,
        "transaction_date": epoch0 + day.astype("timedelta64[D]"),
        "quantity": qty,
        "amount": np.round(price * qty, 2),
        "payment_method": rng.choice(PAYMENTS, n["sales"]),
    })

    lo, hi = int(cfg("dataset.return_lag_days_min")), int(cfg("dataset.return_lag_days_max"))
    returned = rng.choice(sales.order_id.to_numpy(), n["returns"], replace=False)
    returns = pd.DataFrame({
        "return_id": np.arange(1, n["returns"] + 1),
        "order_id": returned,
        "return_date": sales.transaction_date.to_numpy()[returned - 1] + rng.integers(lo, hi + 1, n["returns"]).astype("timedelta64[D]"),
        "reason": rng.choice(REASONS, n["returns"]),
    })

    _plant_canaries(rng, customers, products, sales)
    return {"regions": regions, "stores": stores, "products": products, "customers": customers,
            "sales": sales, "returns": returns}


def _plant_canaries(rng, customers, products, sales) -> None:
    """Overwrite a few generated rows with the row canaries. Rows are picked at random."""
    picks = rng.choice(customers.index.to_numpy(), len(canaries.EMAILS) + len(canaries.NAMES) + len(canaries.PHONES), replace=False)
    it = iter(picks)
    for c in canaries.EMAILS:
        customers.loc[next(it), "email"] = c.value
    for c in canaries.NAMES:
        customers.loc[next(it), "full_name"] = c.value
    for c in canaries.PHONES:
        customers.loc[next(it), "phone"] = c.value
    for i, c in zip(rng.choice(products.index.to_numpy(), len(canaries.PRODUCTS), replace=False), canaries.PRODUCTS):
        products.loc[i, "name"] = c.value
    for i, c in zip(rng.choice(sales.index.to_numpy(), len(canaries.AMOUNTS), replace=False), canaries.AMOUNTS):
        sales.loc[i, "amount"] = float(c.value)


def _copy(conn: psycopg.Connection, table: str, df: pd.DataFrame, batch: int) -> None:
    cols = ", ".join(df.columns)
    with conn.cursor() as cur:
        for start in range(0, len(df), batch):
            buf = io.StringIO()
            df.iloc[start:start + batch].to_csv(buf, index=False, header=False)
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(buf.getvalue())


def load(dsn: str) -> dict[str, float]:
    """Create the schema, generate every table, COPY it in, ANALYZE. Returns timings."""
    t = {}
    t0 = time.perf_counter()
    tables = build(np.random.default_rng(int(cfg("dataset.random_seed"))))
    t["generate_s"] = time.perf_counter() - t0
    batch = int(cfg("workload.copy_batch_rows"))
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(open(SCHEMA_SQL, encoding="utf-8").read())
        t1 = time.perf_counter()
        for name in ("regions", "stores", "products", "customers", "sales", "returns"):
            _copy(conn, name, tables[name], batch)
        t["copy_s"] = time.perf_counter() - t1
        t2 = time.perf_counter()
        conn.execute("ANALYZE")
        t["analyze_s"] = time.perf_counter() - t2
    return t
