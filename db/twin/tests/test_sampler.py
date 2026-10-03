"""Twin column sampler checks that need no database. The twin streams its hero table in
chunks, so a column's synthetic most-common values must be fixed once and shared by every
chunk; otherwise the frequency-rank map would point at values some chunks never hold."""
import numpy as np

from db.twin.build import _column_sampler

# pg_stats-shaped tuples: (n_distinct, null_frac, avg_width, mcv, mcf, histogram_bounds)
DATE_STAT = (900, 0.0, 4, ["2026-09-01", "2026-08-15"], [0.01, 0.008],
             ["2024-01-01", "2025-01-01", "2026-01-01", "2026-09-30"])
TEXT_STAT = (4, 0.0, 5, ["card", "upi", "cash", "wallet"], [0.25, 0.25, 0.25, 0.25], None)
FK_STAT = (12, 0.0, 4, ["7", "3"], [0.3, 0.07], None)


def draw_chunks(draw, sizes):
    out, start = [], 0
    for s in sizes:
        out.append(draw(start, s))
        start += s
    return np.concatenate(out)


def test_pk_is_contiguous_across_chunks():
    draw, _ = _column_sampler(np.random.default_rng(0), "bigint", None, "pk", 0, "order_id")
    assert draw_chunks(draw, [7, 5, 9]).tolist() == list(range(1, 22))


def test_mcv_values_shared_by_every_chunk():
    for typ, stat in (("date", DATE_STAT), ("text", TEXT_STAT)):
        draw, mapping = _column_sampler(np.random.default_rng(0), typ, stat, None, 0, "c")
        twin_mcv = {str(t) for _, t in mapping}
        first, second = draw(0, 20_000), draw(20_000, 20_000)
        for chunk in (first, second):
            seen = {str(v) for v in chunk}
            assert twin_mcv <= seen, (typ, twin_mcv - seen)


def test_fk_rank_map_and_range():
    draw, mapping = _column_sampler(np.random.default_rng(0), "integer", FK_STAT, "fk", 12, "region_id")
    assert mapping == [["7", 1], ["3", 2]]
    vals = draw_chunks(draw, [30_000, 30_000])
    assert vals.min() >= 1 and vals.max() <= 12
    assert abs((vals == 1).mean() - 0.3) < 0.01


def test_no_real_text_value_written():
    draw, _ = _column_sampler(np.random.default_rng(0), "text", TEXT_STAT, None, 0, "payment_method")
    assert not ({"card", "upi", "cash", "wallet"} & set(draw(0, 5_000)))


# Correlations (db/twin/build.py, module docstring). A toy prod table: sales by store, where
# every store sits in one region. pg_stats-shaped stats for both columns plus the bucketed
# table prod would return for the pair (store_id, region_id).
STORE_STAT = (6, 0.0, 4, ["11", "12", "13", "14"], [0.3, 0.2, 0.2, 0.1], None)
REGION_STAT = (3, 0.0, 4, ["7", "8", "9"], [0.5, 0.3, 0.2], None)
STORE_REGION = {"11": "7", "12": "8", "13": "9", "14": "8"}       # the rest of the stores: region 7
JOINT = {("11", "m:7"): 300, ("12", "m:8"): 200, ("13", "m:9"): 200, ("14", "m:8"): 100, (None, "m:7"): 200}


def test_conditional_sampler_keeps_a_correlation_the_independent_one_loses():
    from db.twin.build import _conditional_u
    rng = np.random.default_rng(0)
    draw_store, store_map = _column_sampler(rng, "integer", STORE_STAT, "fk", 6, "store_id")
    draw_region, region_map = _column_sampler(rng, "integer", REGION_STAT, "fk", 3, "region_id")
    twin_store, twin_region = dict(store_map), dict(region_map)
    u_for = _conditional_u(rng, store_map, JOINT, draw_region.intervals)
    stores = draw_store(0, 60_000)
    regions = draw_region(0, 60_000, u=u_for(stores))
    independent = draw_region(0, 60_000)
    for real_store, real_region in STORE_REGION.items():
        rows = stores == twin_store[real_store]
        assert (regions[rows] == twin_region[real_region]).all(), real_store
        assert (independent[rows] == twin_region[real_region]).mean() < 0.6
    rest = ~np.isin(stores, list(twin_store.values()))
    assert rest.any() and (regions[rest] == twin_region["7"]).all()
    for real, share in zip(REGION_STAT[3], REGION_STAT[4]):       # the marginal is kept too
        assert abs((regions == twin_region[real]).mean() - share) < 0.01


def test_conditional_dates_stay_in_their_histogram_bucket():
    from db.twin.build import _conditional_u
    rng = np.random.default_rng(1)
    region = (2, 0.0, 4, ["1", "2"], [0.5, 0.5], None)
    dates = (900, 0.0, 4, [], [], ["2024-01-01", "2025-01-01", "2026-01-01", "2026-09-30"])
    draw_region, region_map = _column_sampler(rng, "integer", region, "fk", 2, "region_id")
    draw_date, _ = _column_sampler(rng, "date", dates, None, 0, "transaction_date")
    joint = {("1", "h:1"): 10, ("2", "h:3"): 10}                   # region 1 only in 2024, region 2 only in 2026
    regions = draw_region(0, 20_000)
    got = draw_date(0, 20_000, u=_conditional_u(rng, region_map, joint, draw_date.intervals)(regions))
    twin = dict(region_map)
    assert max(got[regions == twin["1"]]) <= "2025-01-01"          # day rounding can reach the top bound
    assert min(got[regions == twin["2"]]) >= "2026-01-01"


def test_pairs_with_a_primary_key_second_are_flipped_and_cycles_skipped():
    from db.twin.build import _orient
    meta = {"pk": {("stores", "store_id"), ("sales", "order_id")}}
    pairs = [("stores", "region_id", "store_id"), ("sales", "a", "b"), ("sales", "b", "a"), ("sales", "c", "b")]
    assert _orient(meta, pairs, lambda _: None) == [("stores", "store_id", "region_id"), ("sales", "a", "b")]


def test_on_screen_twin_label_is_the_builders():
    from dashboard.data import LABELS
    from db.twin.build import LABEL
    assert LABELS["twin"] == LABEL
