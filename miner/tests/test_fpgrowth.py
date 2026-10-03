"""Miner unit tests on synthetic hashed templates with known weights."""
from contracts.validate import errors
from miner.fpgrowth import candidates, frequent_itemsets

T, U = "t_aaaaaaaa", "t_bbbbbbbb"
A, B, C, D, E = "c_00000001", "c_00000002", "c_00000003", "c_00000004", "c_00000005"
META = [{"col": A, "n_distinct": 12}, {"col": B, "n_distinct": 1000}, {"col": C, "n_distinct": 2},
        {"col": D, "n_distinct": 500}, {"col": E, "n_distinct": 50}]


def tpl(tid, total_ms, cols):
    return {"template_id": tid, "sql": "SELECT ?", "calls": 1, "mean_ms": total_ms, "total_ms": total_ms,
            "columns": [{"table": t, "col": c, "role": r} for t, c, r in cols]}


def test_weighted_support_is_share_of_time():
    # {A:EQ} appears in a 900 ms and a 100 ms basket; {B:RANGE} only in the 100 ms one.
    items = [{f"{A}:EQ"}, {f"{A}:EQ", f"{B}:RANGE"}]
    found = dict(frequent_itemsets(items, [900.0, 100.0]))
    assert found[frozenset({f"{A}:EQ"})] == 1.0
    assert abs(found[frozenset({f"{B}:RANGE"})] - 0.1) < 1e-9


def test_cheap_frequent_queries_do_not_dominate():
    # 50 cheap baskets on E, one expensive basket on A+B: time weight, not count, decides.
    tps = [tpl(f"q_{i:08x}", 1.0, [(T, E, "EQ")]) for i in range(50)] + [tpl("q_ffffffff", 40000.0, [(T, A, "EQ"), (T, B, "RANGE")])]
    cands = candidates(tps, META)
    assert cands[0]["columns"] == [A, B]
    assert all(c["columns"] != [E] for c in cands)     # E's support is under 5% of time


def test_eq_columns_lead_then_range_then_order():
    cands = candidates([tpl("q_00000001", 100.0, [(T, D, "ORDER"), (T, B, "RANGE"), (T, A, "EQ")])], META)
    assert cands[0]["columns"] == [A, B, D]


def test_low_distinct_column_cannot_lead():
    cands = candidates([tpl("q_00000001", 100.0, [(T, C, "EQ"), (T, B, "RANGE")])], META)
    assert all(c["columns"][0] != C for c in cands)


def test_max_three_columns():
    cands = candidates([tpl("q_00000001", 100.0, [(T, A, "EQ"), (T, D, "EQ"), (T, B, "RANGE"), (T, E, "ORDER")])], META)
    assert all(len(c["columns"]) <= 3 for c in cands)


def test_covered_by_existing_index_is_dropped():
    tps = [tpl("q_00000001", 100.0, [(T, A, "EQ"), (T, B, "RANGE")])]
    cands = candidates(tps, META, existing_indexes=[(T, [A, B])])
    assert [A, B] not in [c["columns"] for c in cands] and [A] not in [c["columns"] for c in cands]


def test_itemsets_spanning_two_tables_are_not_candidates():
    cands = candidates([tpl("q_00000001", 100.0, [(T, A, "EQ"), (U, D, "EQ")])], META)
    assert all(len({c["table"]}) == 1 for c in cands)
    assert [A, D] not in [c["columns"] for c in cands]


def test_candidates_match_contract():
    for c in candidates([tpl("q_00000001", 100.0, [(T, A, "EQ"), (T, B, "RANGE")])], META):
        assert errors("Candidate", c) == []


def test_rewritten_shape_adds_index_only_useful_after_rewrite():
    # The original wraps B in a function (no role); its rewrite makes B a range. Q2 shape:
    # D joins, B is filtered only after the rewrite. The other template keeps the total honest.
    from miner.fpgrowth import with_rewritten_shapes
    q2 = tpl("q_00000002", 300.0, [(T, D, "JOIN")])
    other = tpl("q_00000003", 100.0, [(T, A, "EQ")])
    assert [D, B] not in [c["columns"] for c in candidates([q2, other], META)]
    rw = [{"template_id": "q_00000002", "rule_id": "date_trunc_eq_to_range",
           "columns": [{"table": T, "col": D, "role": "JOIN"}, {"table": T, "col": B, "role": "RANGE"}]}]
    cands = {tuple(c["columns"]): c for c in candidates(with_rewritten_shapes([q2, other], rw), META)}
    assert (D, B) in cands
    assert cands[(D, B)]["support"] == 0.75                 # 300 of 400 ms: each template counted once
    assert cands[(A,)]["support"] == 0.25
