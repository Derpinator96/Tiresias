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

Sales are generated and copied in chunks of workload.copy_batch_rows, so memory stays flat
at any sales_rows (50,000,000 does not fit in memory as one DataFrame). Foreign keys are
added after the load (db/foreign_keys.sql).
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
FOREIGN_KEYS_SQL = os.path.join(os.path.dirname(__file__), "foreign_keys.sql")

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


def sizes(sales_rows: int | None = None) -> dict[str, int]:
    """Row counts per table. sales_rows overrides dataset.sales_rows (plan generation loads a
    smaller QuickMart copy into pg-bench)."""
    sales = int(cfg("dataset.sales_rows") if sales_rows is None else sales_rows)
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


def _dates():
    d0, d1 = date.fromisoformat(cfg("dataset.date_start")), date.fromisoformat(cfg("dataset.date_end"))
    return np.datetime64(d0), (d1 - d0).days + 1


def build_parents(rng: np.random.Generator, n: dict[str, int]) -> dict[str, pd.DataFrame]:
    """regions, stores, products and customers, with their row canaries planted."""
    hero = int(cfg("dataset.hero_region_id"))
    epoch0, n_days = _dates()

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

    _plant_parent_canaries(rng, customers, products)
    return {"regions": regions, "stores": stores, "products": products, "customers": customers}


class SalesPlan:
    """Everything sales generation needs before the first chunk: which orders are returned
    (so their dates can be kept while chunks stream past) and which rows carry canary amounts."""

    def __init__(self, rng: np.random.Generator, n: dict[str, int], parents: dict[str, pd.DataFrame]):
        hero = int(cfg("dataset.hero_region_id"))
        self.n = n
        self.hero = hero
        self.hero_share = float(cfg("dataset.hero_region_share"))
        self.epoch0, self.n_days = _dates()
        self.day_p = _day_weights(self.n_days)
        regions, stores, products = parents["regions"], parents["stores"], parents["products"]
        self.others = np.array([r for r in regions.region_id if r != hero])
        self.stores_by_region = {r: stores.store_id[stores.region_id == r].to_numpy() for r in regions.region_id}
        # Products: the top share of products (a random choice) gets top_product_revenue_share
        # of all sales, so it earns about that share of revenue.
        top_n = round(n["products"] * float(cfg("dataset.top_product_share")))
        order = rng.permutation(products.product_id.to_numpy())
        self.top, self.rest = order[:top_n], order[top_n:]
        self.top_draw = float(cfg("dataset.top_product_revenue_share"))
        self.price = products.set_index("product_id").unit_price.to_numpy()
        # Returned orders, in return_id order, and their sale day filled in chunk by chunk.
        self.returned = rng.choice(n["sales"], n["returns"], replace=False) + 1
        self._ret_order = np.argsort(self.returned)
        self._ret_sorted = self.returned[self._ret_order]
        self.returned_day = np.full(n["returns"], -1, dtype=np.int64)
        # Global sales rows (0-based) that carry the canary amounts.
        self.canary_rows = dict(zip(rng.choice(n["sales"], len(canaries.AMOUNTS), replace=False).tolist(),
                                    [float(c.value) for c in canaries.AMOUNTS]))


def sales_chunk(rng: np.random.Generator, plan: SalesPlan, start: int, size: int) -> pd.DataFrame:
    """Sales rows start .. start + size - 1 (0-based). Order IDs are start + 1 onwards."""
    # Pick the region first (hero region at hero_share, others uniform), then a store in that
    # region, so each sale carries its store's region_id.
    is_hero = rng.random(size) < plan.hero_share
    region = np.where(is_hero, plan.hero, rng.choice(plan.others, size))
    store = np.empty(size, dtype=np.int64)
    for r, ids in plan.stores_by_region.items():
        mask = region == r
        store[mask] = rng.choice(ids, mask.sum())
    from_top = rng.random(size) < plan.top_draw
    product = np.where(from_top, rng.choice(plan.top, size), rng.choice(plan.rest, size))
    day = rng.choice(plan.n_days, size, p=plan.day_p)
    q_lo, q_hi = cfg("dataset.quantity_range")
    qty = rng.integers(q_lo, q_hi + 1, size)
    order_id = np.arange(start + 1, start + size + 1)
    chunk = pd.DataFrame({
        "order_id": order_id,
        "customer_id": rng.integers(1, plan.n["customers"] + 1, size),
        "product_id": product,
        "store_id": store,
        "region_id": region,
        "transaction_date": plan.epoch0 + day.astype("timedelta64[D]"),
        "quantity": qty,
        "amount": np.round(plan.price[product - 1] * qty, 2),
        "payment_method": rng.choice(PAYMENTS, size),
    })
    for row, amount in plan.canary_rows.items():
        if start <= row < start + size:
            chunk.loc[row - start, "amount"] = amount
    lo = np.searchsorted(plan._ret_sorted, start + 1)
    hi = np.searchsorted(plan._ret_sorted, start + size, side="right")
    plan.returned_day[plan._ret_order[lo:hi]] = day[plan._ret_sorted[lo:hi] - start - 1]
    return chunk


def build_returns(rng: np.random.Generator, plan: SalesPlan) -> pd.DataFrame:
    """Returns follow their sale by return_lag_days_min to _max days. Call after every chunk."""
    assert (plan.returned_day >= 0).all(), "every sales chunk must be generated before returns"
    lo, hi = int(cfg("dataset.return_lag_days_min")), int(cfg("dataset.return_lag_days_max"))
    n = plan.n["returns"]
    lag = rng.integers(lo, hi + 1, n)
    return pd.DataFrame({
        "return_id": np.arange(1, n + 1),
        "order_id": plan.returned,
        "return_date": plan.epoch0 + (plan.returned_day + lag).astype("timedelta64[D]"),
        "reason": rng.choice(REASONS, n),
    })


def _plant_parent_canaries(rng, customers, products) -> None:
    """Overwrite a few generated rows with the row canaries. Rows are picked at random.
    Sale amount canaries are planted by sales_chunk (SalesPlan.canary_rows)."""
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


def _copy(conn: psycopg.Connection, table: str, df: pd.DataFrame, batch: int) -> None:
    cols = ", ".join(df.columns)
    with conn.cursor() as cur:
        for start in range(0, len(df), batch):
            buf = io.StringIO()
            df.iloc[start:start + batch].to_csv(buf, index=False, header=False)
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(buf.getvalue())


def load(dsn: str, sales_rows: int | None = None, log=print) -> dict[str, float]:
    """Create the schema, generate every table, COPY it in, add foreign keys, ANALYZE.
    Returns timings in seconds."""
    t = {}
    n = sizes(sales_rows)
    rng = np.random.default_rng(int(cfg("dataset.random_seed")))
    batch = int(cfg("workload.copy_batch_rows"))
    t0 = time.perf_counter()
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(open(SCHEMA_SQL, encoding="utf-8").read())
        parents = build_parents(rng, n)
        for name in ("regions", "stores", "products", "customers"):
            _copy(conn, name, parents[name], batch)
        plan = SalesPlan(rng, n, parents)
        for start in range(0, n["sales"], batch):
            _copy(conn, "sales", sales_chunk(rng, plan, start, min(batch, n["sales"] - start)), batch)
            done = min(start + batch, n["sales"])
            if done % (batch * 20) == 0 or done == n["sales"]:
                log(f"sales: {done:,} of {n['sales']:,} rows after {time.perf_counter() - t0:.0f} s")
        _copy(conn, "returns", build_returns(rng, plan), batch)
        t["generate_and_copy_s"] = time.perf_counter() - t0
        t1 = time.perf_counter()
        conn.execute(open(FOREIGN_KEYS_SQL, encoding="utf-8").read())
        t["foreign_keys_s"] = time.perf_counter() - t1
        t2 = time.perf_counter()
        conn.execute("ANALYZE")
        t["analyze_s"] = time.perf_counter() - t2
    t["total_s"] = time.perf_counter() - t0
    return t
