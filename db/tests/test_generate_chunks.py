"""Chunked generation checks that need no database (run anywhere with numpy and pandas).

Sales stream out in chunks so 50,000,000 rows fit in memory. These tests generate a small
QuickMart in memory with a deliberately awkward chunk size and check that streaming keeps
the doc's rules: contiguous order IDs, each sale in its store's region, returns 1 to 30 days
after their own sale, and every canary amount planted exactly once.
"""
import numpy as np
import pandas as pd
import pytest

from common.config import cfg
from db import canaries, generate

SALES = 20_011     # small, and not a multiple of the chunk size
CHUNK = 3_001


@pytest.fixture(scope="module")
def data():
    n = generate.sizes(SALES)
    rng = np.random.default_rng(0)
    parents = generate.build_parents(rng, n)
    plan = generate.SalesPlan(rng, n, parents)
    chunks = [generate.sales_chunk(rng, plan, s, min(CHUNK, SALES - s)) for s in range(0, SALES, CHUNK)]
    sales = pd.concat(chunks, ignore_index=True)
    returns = generate.build_returns(rng, plan)
    return n, parents, sales, returns


def test_sizes_override_scales_children():
    n = generate.sizes(SALES)
    assert n["sales"] == SALES
    assert n["customers"] == round(SALES * cfg("dataset.customers_per_sale"))
    assert generate.sizes()["sales"] == cfg("dataset.sales_rows")


def test_order_ids_contiguous(data):
    _, _, sales, _ = data
    assert sales.order_id.tolist() == list(range(1, SALES + 1))


def test_sale_region_is_store_region(data):
    _, parents, sales, _ = data
    store_region = parents["stores"].set_index("store_id").region_id
    assert (sales.region_id.to_numpy() == store_region.loc[sales.store_id].to_numpy()).all()


def test_returns_follow_their_own_sale(data):
    _, _, sales, returns = data
    sale_date = sales.set_index("order_id").transaction_date.loc[returns.order_id].to_numpy()
    lag = (returns.return_date.to_numpy() - sale_date).astype("timedelta64[D]").astype(int)
    assert lag.min() >= cfg("dataset.return_lag_days_min")
    assert lag.max() <= cfg("dataset.return_lag_days_max")
    assert returns.order_id.is_unique


def test_canary_amounts_planted_once(data):
    _, _, sales, _ = data
    for c in canaries.AMOUNTS:
        assert (sales.amount == float(c.value)).sum() >= 1, c.value


def test_parent_canaries_planted(data):
    _, parents, _, _ = data
    cust, prod = parents["customers"], parents["products"]
    for c in canaries.EMAILS:
        assert (cust.email == c.value).sum() == 1
    for c in canaries.PRODUCTS:
        assert (prod.name == c.value).sum() == 1


def test_returns_need_every_chunk_first():
    n = generate.sizes(SALES)
    rng = np.random.default_rng(0)
    plan = generate.SalesPlan(rng, n, generate.build_parents(rng, n))
    generate.sales_chunk(rng, plan, 0, CHUNK)
    with pytest.raises(AssertionError):
        generate.build_returns(rng, plan)
