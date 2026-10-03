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
