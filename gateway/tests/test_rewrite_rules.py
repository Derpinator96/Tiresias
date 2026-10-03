"""Rewrite rule library unit tests: shape matching on hashed SQL, value-checked rewrites on
real SQL, and no rewrite where values would make it wrong."""
import pytest

from gateway import rewrite_rules as rr

Q2 = ("SELECT p.category, SUM(s.amount) FROM sales s JOIN products p ON p.product_id = s.product_id "
      "JOIN stores st ON st.store_id = s.store_id WHERE st.region_id = 7 "
      "AND date_trunc('month', s.transaction_date) = '2026-09-01' GROUP BY p.category")
Q2_HASHED = ("SELECT p.c_00000001, SUM(s.c_00000002) FROM t_00000001 AS s JOIN t_00000002 AS p ON p.c_00000003 = s.c_00000004 "
             "JOIN t_00000003 AS st ON st.c_00000005 = s.c_00000006 WHERE st.c_00000007 = ? "
             "AND DATE_TRUNC(?, s.c_00000008) = ? GROUP BY p.c_00000001")


def test_q2_rewrite_is_the_docs_expected_range():
    out = rr.rewrite(Q2, "date_trunc_eq_to_range")
    assert "(s.transaction_date >= '2026-09-01' AND s.transaction_date < '2026-10-01')" in out
    assert "DATE_TRUNC" not in out.upper() and "st.region_id = 7" in out


def test_q2_shape_matches_on_hashed_sql_and_shows_only_placeholders():
    assert rr.matching(Q2_HASHED) == ["date_trunc_eq_to_range"]
    shape = rr.rewrite_shape(Q2_HASHED, "date_trunc_eq_to_range")
    assert "(s.c_00000008 >= ? AND s.c_00000008 < ?)" in shape and "'" not in shape


@pytest.mark.parametrize("d,unit,end", [("2026-12-01", "month", "2027-01-01"), ("2026-01-01", "year", "2027-01-01"),
                                        ("2026-09-30", "day", "2026-10-01")])
def test_unit_boundaries(d, unit, end):
    out = rr.rewrite(f"SELECT 1 FROM t WHERE date_trunc('{unit}', c) = '{d}'", "date_trunc_eq_to_range")
    assert f"c >= '{d}' AND c < '{end}'" in out


def test_off_boundary_date_is_not_rewritten():
    # date_trunc('month', c) is never 2026-09-15, so the original returns nothing; a range would not.
    with pytest.raises(rr.NotApplicable):
        rr.rewrite("SELECT 1 FROM t WHERE date_trunc('month', c) = '2026-09-15'", "date_trunc_eq_to_range")


def test_unsupported_unit_is_not_rewritten():
    with pytest.raises(rr.NotApplicable):
        rr.rewrite("SELECT 1 FROM t WHERE date_trunc('week', c) = '2026-09-07'", "date_trunc_eq_to_range")


def test_extract_year():
    out = rr.rewrite("SELECT 1 FROM t WHERE EXTRACT(YEAR FROM d) = 2025", "extract_year_eq_to_range")
    assert "d >= '2025-01-01' AND d < '2026-01-01'" in out
    assert rr.matching("SELECT 1 FROM t WHERE EXTRACT(YEAR FROM c_00000001) = ?") == ["extract_year_eq_to_range"]


def test_or_same_column_to_in():
    out = rr.rewrite("SELECT SUM(a) FROM t WHERE x > 1 AND (r = 3 OR r = 7 OR r = 9)", "or_same_column_to_in")
    assert "r IN (3, 7, 9)" in out and "x > 1" in out


@pytest.mark.parametrize("sql", [
    "SELECT 1 FROM t WHERE r = 3 OR q = 7",            # different columns
    "SELECT 1 FROM t WHERE r = 3 OR r > 7",            # not all equalities
    "SELECT 1 FROM t WHERE r = 3",                     # no OR
    "SELECT 1 FROM t WHERE date_trunc('month', c) > '2026-09-01'",   # not an equality
])
def test_no_false_matches(sql):
    assert rr.matching(sql) == []
