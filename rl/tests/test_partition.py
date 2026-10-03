"""Partition step of the search (rl/search.py partition_keys, add_partition). The unit tests use a
fake gateway; the live test runs /ai/rl/run on the seeded stack (tools container, after make
seed): Q3 gets a monthly partition measured on the twin, the twin is left as it was, and the
chosen configuration flows through /v1/approve with the partition steps and the sharding advice."""
import os

import httpx
import psycopg
import pytest

from common.config import cfg
from contracts.validate import errors
from db import run_q1, workload
from models.gnn.predictor import CostPredictor
from rl import search

T, BIG, Q = "t_aaaaaaaa", "t_bbbbbbbb", "q_00000001"
D, D2, N = "c_0000000d", "c_000000d2", "c_0000000a"
IDX = {"cand_id": "cand_00000001", "table": T, "columns": [N], "support": 1.0,
       "evidence": {"items": [f"{N}:EQ"], "templates": [Q]}}


def meta(col, table, type_class):
    return {"table": table, "col": col, "type_class": type_class}


def test_partition_keys_are_filtered_date_columns_largest_table_first(monkeypatch):
    monkeypatch.setattr(search, "cfg", lambda k: 2 if k == "rl.partition_max_keys" else None)
    cols = [meta(D, T, "date"), meta(D2, BIG, "date"), meta(N, T, "number"), meta("c_0000000e", T, "date")]
    tables = [{"table": T, "size_mb": 10.0}, {"table": BIG, "size_mb": 900.0}]
    templates = [{"total_ms": 5.0, "columns": [{"table": T, "col": D, "role": "RANGE"}, {"table": T, "col": D, "role": "RANGE"},
                                               {"table": T, "col": N, "role": "EQ"}]},
                 {"total_ms": 1.0, "columns": [{"table": BIG, "col": D2, "role": "EQ"},
                                               {"table": T, "col": "c_0000000e", "role": "GROUP"}]}]
    keys = search.partition_keys(templates, cols, tables)
    assert [(k["table"], k["column"]) for k in keys] == [(BIG, D2), (T, D)]   # a GROUP-only date column is not a key
    assert all(k["type"] == "partition" and k["scheme"] == "range_month" for k in keys)
    monkeypatch.setattr(search, "cfg", lambda k: 1 if k == "rl.partition_max_keys" else None)
    assert len(search.partition_keys(templates, cols, tables)) == 1


def fake_twin(after_by_key, storage_mb=5.0, calls=None):
    """Twin after_ms per frozenset of action keys ("i" index, "p" partition); before is 1000."""
    def post(path, body, timeout=None):
        assert path == "/v1/simulate/twin"
        key = frozenset("p" if a["type"] == "partition" else "i" for a in body["actions"])
        if calls is not None:
            calls.append((key, timeout))
        return {"config_id": body["config_id"], "source": "twin", "write_ms_delta": 0.01, "runs": 5,
                "storage_mb_delta": storage_mb * len(key),
                "templates": [{"template_id": Q, "before_ms": 1000.0, "after_ms": after_by_key[key]}]}
    return post


def searcher(monkeypatch, post):
    monkeypatch.setattr(search.gw, "post", post)
    monkeypatch.setattr(search, "_TWIN", {})
    model = CostPredictor()
    model.ms_per_cost = 0.02
    rl = search.QLearningSearch([{"template_id": Q, "calls": 1, "total_ms": 1.0, "columns": []}], [],
                                [{"table": T, "size_mb": 100.0}], model, None, q={})
    rl.trace.final_choice = "best measured on the twin"
    return rl


PART = {"type": "partition", "table": T, "column": D, "scheme": "range_month"}


def chosen_index_config(rl, score):
    config = search._config([{"type": "add_index", "table": T, "columns": [N], "cand_id": IDX["cand_id"]}], "q_learning")
    rl.trace.top_configs = [{"cand_ids": [IDX["cand_id"]], "config_id": config["config_id"], "actions": config["actions"],
                             "disagreement": 0.0, "twin": {}, "measured_drop": 0.5, "measured_reward": score,
                             "score": score, "chosen": True}]
    return config


def test_partition_is_kept_only_when_its_measured_score_beats_the_chosen_config(monkeypatch):
    calls = []
    rl = searcher(monkeypatch, fake_twin({frozenset("ip"): 100.0}, calls=calls))
    config = rl.add_partition(chosen_index_config(rl, 0.3), [PART])
    assert errors("Config", config) == []
    assert [a["type"] for a in config["actions"]] == ["add_index", "partition"]
    # Same formula as the re-check: drop 0.9, one index 0.1, storage 0.25 x 10 MB / 25 MB = 0.1.
    [k] = rl.trace.partition["keys"]
    assert k["measured_drop"] == pytest.approx(0.9) and k["score"] == pytest.approx(0.7)
    assert rl.trace.partition["kept"] == {"table": T, "column": D} and rl.trace.partition["base_score"] == 0.3
    [entry] = rl.trace.top_configs
    assert entry["chosen"] and entry["config_id"] == config["config_id"] and entry["actions"] == config["actions"]
    assert entry["without_partition"]["score"] == 0.3
    assert calls == [(frozenset("ip"), float(cfg("rl.partition_twin_timeout_s")))]   # the long timeout


def test_partition_that_does_not_pay_is_reported_and_not_kept(monkeypatch):
    rl = searcher(monkeypatch, fake_twin({frozenset("ip"): 450.0}))
    before = chosen_index_config(rl, 0.4)
    assert rl.add_partition(before, [PART]) == before          # 0.55 - 0.1 - 0.1 = 0.35 < 0.4
    assert rl.trace.partition["kept"] is None and rl.trace.partition["keys"][0]["score"] == pytest.approx(0.35)
    assert "without_partition" not in rl.trace.top_configs[0]


def test_partition_alone_when_no_index_paid_and_skipped_without_a_measurement(monkeypatch):
    rl = searcher(monkeypatch, fake_twin({frozenset("p"): 200.0}))
    rl.trace.top_configs = [{"cand_ids": ["x"], "score": -0.1, "chosen": False}]
    config = rl.add_partition(search._config([], "q_learning"), [PART])
    assert [a["type"] for a in config["actions"]] == ["partition"] and errors("Config", config) == []
    assert rl.trace.top_configs[-1]["chosen"] and rl.trace.top_configs[-1]["score"] == pytest.approx(0.75)   # 0.8 - 0.05 storage
    rl.trace.final_choice = "best predicted (no twin measurement succeeded)"
    assert rl.add_partition(search._config([], "q_learning"), [PART])["actions"] == []
    assert rl.trace.partition["skipped"]


def test_weights_of_templates_no_longer_slow_fall_back_to_call_shares():
    # A drift window can name only a template whose statistics were reset since (this file's
    # live test resets Q3): the workload time would be 0 and every reward a division by zero.
    tpl = [{"template_id": Q, "calls": 3, "total_ms": 1.0, "columns": []}]
    assert search.GreedySearch(tpl, [], [], CostPredictor(), {"q_0000dead": 1.0}).weights == {Q: 1.0}
    assert search.GreedySearch(tpl, [], [], CostPredictor(), {Q: 0.5, "q_0000dead": 0.5}).weights == {Q: 0.5}


# ---- live: tools container on the seeded bt stack -------------------------------------------
def twin_state(conn):
    tables = conn.execute("SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace "
                          "AND relkind IN ('r', 'p') ORDER BY 1").fetchall()
    sales = conn.execute("SELECT 'sales'::regclass::oid, count(*), max(order_id) FROM sales").fetchone()
    indexes = conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1").fetchall()
    return tables, sales, indexes


def dehash(text):
    return httpx.post(os.environ["GATEWAY_URL"] + "/v1/answers/dehash", timeout=60,
                      json={"question_id": "qn_00000000", "text": text, "numbers": []}).json()["text"]


Q3_PREFIX = "SELECT region_id, SUM(amount), COUNT(*) FROM sales"


def reset_q3():
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as c:
        for (qid,) in c.execute("SELECT queryid FROM pg_stat_statements WHERE query LIKE %s", (Q3_PREFIX + "%",)).fetchall():
            c.execute("SELECT pg_stat_statements_reset(0, 0, %s)", (qid,))


@pytest.fixture
def q3_running():
    """Q3 in the workload for this test only (make seed leaves it out while workload.q3_in_seed
    is false); its statistics are reset afterwards, so later suites see the seeded workload."""
    reset_q3()
    with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
        for _ in range(int(cfg("workload.q3_runs"))):
            conn.execute(workload.q3_sql()).fetchall()
    yield
    reset_q3()


@pytest.mark.skipif("AI_URL" not in os.environ or "TWIN_DSN" not in os.environ, reason="needs the seeded stack")
def test_q3_gets_a_partition_measured_on_the_twin_and_the_twin_is_restored(q3_running):
    with psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as twin:
        start = twin_state(twin)
    r = httpx.post(os.environ["AI_URL"] + "/ai/rl/run", json={}, timeout=1800)
    assert r.status_code == 200, r.text
    rl = r.json()
    assert errors("Config", rl["config"]) == []
    part = rl["partition"]
    print("\npartition step:", {k: v for k, v in part.items() if k != "keys"},
          [{f: k.get(f) for f in ("measured_drop", "score", "write_ms_delta", "twin")} for k in part["keys"]])
    assert part["keys"] and all("score" in k for k in part["keys"]), part
    [action] = [a for a in rl["config"]["actions"] if a["type"] == "partition"]
    assert dehash(f"{action['table']} {action['column']}") == "sales transaction_date"
    # Measured on the twin: Q3's template got faster with the partitioned copy.
    kept = next(k for k in part["keys"] if k["column"] == action["column"])
    q3 = next(t for t in httpx.get(os.environ["GATEWAY_URL"] + "/v1/templates/slow", timeout=60).json()
              if dehash(t["template_id"]).startswith(f'query "{Q3_PREFIX}'))
    t3 = next(t for t in kept["twin"]["templates"] if t["template_id"] == q3["template_id"])
    print("Q3 on the twin:", t3, "storage MB:", kept["twin"]["storage_mb"])
    assert t3["after_ms"] < t3["before_ms"]
    chosen = [e for e in rl["top_configs"] if e["chosen"]]
    assert len(chosen) == 1 and chosen[0]["partition"] == part["kept"]
    with psycopg.connect(os.environ["TWIN_DSN"], autocommit=True) as twin:
        assert twin_state(twin) == start, "the twin must be left exactly as it was"

    files = httpx.post(os.environ["GATEWAY_URL"] + "/v1/approve", json=rl["config"], timeout=120)
    assert files.status_code == 200, files.text
    migration = files.json()["files"]["migration.sql"]
    assert 'PARTITION BY RANGE ("transaction_date")' in migration
    assert "Sharding (written advice only" in migration
