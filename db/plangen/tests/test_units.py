"""Plan generation unit tests: no database and no benchmark kits needed."""
import json
import re

import pytest

from common.config import cfg
from db import canaries
from db.plangen import queries, quickmart_templates, run, setups

N = cfg("plan_generation.parameter_sets_per_query")


def test_split_statements_drops_comments_and_blanks():
    text = "-- start query 1 in stream 0\nselect 1\nfrom t;\n\n-- end\nselect 2;\n"
    assert queries.split_statements(text) == ["select 1\nfrom t", "select 2"]


def test_fix_tpch_interval_and_limit():
    sql = "select x from lineitem where l_shipdate <= date '1998-12-01' - interval '90' day (3) limit -1"
    fixed = queries.fix_tpch(sql)
    assert "day (3)" not in fixed and "limit" not in fixed.lower()
    assert fixed.endswith("interval '90' day")


def test_tpch_skips_view_template():
    assert 15 not in queries.TPCH_TEMPLATES and len(queries.TPCH_TEMPLATES) == 21


def test_setup_counts_within_config():
    lo, hi = cfg("plan_generation.index_setups_per_query_min"), cfg("plan_generation.index_setups_per_query_max")
    sample_index_sql = "\n".join(f"create index i{i} on store_sales (ss_{'sold_date_sk' if i % 2 else 'item_sk'});"
                                 for i in range(10))
    for s in (setups.QUICKMART, setups.TPCH, setups.dsb_setups(sample_index_sql, 1)):
        assert lo <= len(s) <= hi
        assert all(re.fullmatch(r"s_[a-z0-9_]+", sid) for sid in s)   # decision H


def test_dsb_setups_split_full_file():
    sql = "-- header\n" + "\n".join(f"CREATE INDEX i{i} ON t (c{i}{'_date_sk' if i < 3 else ''});" for i in range(9))
    s = setups.dsb_setups(sql, 7)
    assert len(s["s_dsb_all"]) == 9 and s["s_dsb_base"] == []
    assert sorted(s["s_dsb_half_a"] + s["s_dsb_half_b"]) == sorted(s["s_dsb_all"])
    assert len(s["s_dsb_dates"]) == 3
    assert setups.dsb_setups(sql, 7) == s   # seeded


def test_quickmart_instances_deterministic_and_safe():
    a = quickmart_templates.instances(N, 1)
    assert a == quickmart_templates.instances(N, 1)
    assert {t for t, demo, _ in a if demo} >= {"qm/q1", "qm/q2"}
    values = [c.value for c in canaries.ALL]
    for tid, _, sqls in a:
        assert len(sqls) == N and len(set(sqls)) > 1, tid
        assert all("{" not in s for s in sqls), tid
        assert not any(v in s for v in values for s in sqls), tid


def test_quickmart_q1_matches_demo_shape():
    q1 = dict((t, s) for t, _, s in quickmart_templates.instances(2, 1))["qm/q1"][0]
    assert re.fullmatch(r"SELECT SUM\(amount\) FROM sales WHERE region_id = \d+ AND transaction_date >= '\d{4}-\d\d-\d\d'", q1)


PLAN = {"Plan": {"Node Type": "Aggregate", "Plan Rows": 1, "Plans": [
    {"Node Type": "Seq Scan", "Relation Name": "sales", "Plan Rows": 1000}]}}


def test_shape_hash_buckets_rows():
    other = json.loads(json.dumps(PLAN))
    other["Plan"]["Plans"][0]["Plan Rows"] = 700            # same log2 bucket as 1,000 at width 2
    far = json.loads(json.dumps(PLAN))
    far["Plan"]["Plans"][0]["Plan Rows"] = 1_000_000        # different regime
    b = cfg("plan_generation.shape_rows_log2_bucket")
    assert run.shape_hash(PLAN, b) == run.shape_hash(other, b) != run.shape_hash(far, b)


def test_plan_uid_stable_and_distinct():
    assert run.plan_uid("dsb", "t", 1, "s_a") == run.plan_uid("dsb", "t", 1, "s_a")
    assert run.plan_uid("dsb", "t", 1, "s_a") != run.plan_uid("dsb", "t", 2, "s_a")


def fake_wl(n_templates):
    tpl = [(f"x/t{i}", False, [f"select {i}, {p}" for p in range(N)]) for i in range(n_templates)]
    return {db: {"templates": tpl, "setups": {"s_base": [], "s_two": ["create index on t (c)"]}}
            for db in ("quickmart", "tpch", "dsb")}


@pytest.mark.parametrize("n_templates", [5, 60])
def test_sample_plan_size_and_coverage(n_templates):
    size = cfg("plan_generation.early_sample_size")
    plan = run.sample_plan(fake_wl(n_templates), size)
    tasks = [t for *_, ts in plan for t in ts]
    assert len(tasks) == min(size, 3 * 3 * n_templates)
    assert {t[0] for t in tasks} == {"quickmart", "tpch", "dsb"}
    if n_templates == 60:   # trimmed: every database still covers most templates at param set 0
        for db in ("quickmart", "tpch", "dsb"):
            assert len({t[1] for t in tasks if t[0] == db}) >= 60


def test_dedupe_keeps_few_copies_and_counts(tmp_path):
    keep = cfg("plan_generation.max_copies_per_shape")
    raw = tmp_path / "raw.jsonl"
    recs = [{"plan_uid": f"u{i}", "database": "dsb", "template_id": "t", "param_set": i, "setup_id": "s_dsb_base",
             "timed_out": False, "error": None, "shape_hash": "same", "plan": {}} for i in range(keep + 4)]
    recs.append({**recs[0], "plan_uid": "err", "error": "boom", "shape_hash": None})
    recs.append(recs[1])   # a resumed run wrote a duplicate line
    raw.write_text("".join(json.dumps(r) + "\n" for r in recs))
    s = run.dedupe(raw, tmp_path / "plans.jsonl", tmp_path / "summary.json", log=lambda m: None)
    assert s["kept"] == keep
    assert s["per_database"]["dsb"]["errors"] == 1
    assert s["per_database"]["dsb"]["runs"] == keep + 5
