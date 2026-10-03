"""scripts/plans_web_sample.aggregate on a tiny in-memory plans list (no Docker, no services)."""
from scripts.plans_web_sample import aggregate, node_count


def plan(root, *kids):
    return {"Node Type": root, "Plans": [k if isinstance(k, dict) else plan(k) for k in kids]}


def rec(db, tid, runtime, timed_out=False, tree=None):
    return {"database": db, "template_id": tid, "timed_out": timed_out, "runtime_ms": runtime,
            "plan": {"Plan": tree or plan("Aggregate", plan("Seq Scan"))}}


TEMPLATES = {("qm", "q1"): ("SELECT 1", True), ("qm", "q9"): ("SELECT 9", False)}


def test_node_count_walks_the_tree():
    assert node_count(plan("Aggregate", plan("Hash Join", "Seq Scan", "Hash"))) == 4


def test_aggregate_per_template():
    plans = [rec("qm", "q1", 10.0, tree=plan("Aggregate", plan("Hash Join", "Seq Scan", "Seq Scan"))),
             rec("qm", "q1", 30.0), rec("qm", "q1", 20.0), rec("qm", "q1", None, timed_out=True),
             rec("tpch", "q01", 5.5)]
    out = aggregate(plans, TEMPLATES)
    assert [(e["database"], e["template_id"]) for e in out] == [("qm", "q1"), ("qm", "q9"), ("tpch", "q01")]
    q1, q9, t1 = out
    assert q1 == {"database": "qm", "template_id": "q1", "demo": True, "sql": "SELECT 1", "plans": 4,
                  "median_runtime_ms": 20.0, "max_runtime_ms": 30.0, "timed_out": 1, "nodes": 4,
                  "top_ops": ["Seq Scan", "Aggregate", "Hash Join"]}
    # a template with no kept plan keeps its SQL and reports nothing measured
    assert q9["plans"] == 0 and q9["median_runtime_ms"] is None and q9["nodes"] is None and q9["sql"] == "SELECT 9"
    # a plan whose template is unknown is still counted, with no SQL
    assert t1["sql"] is None and t1["plans"] == 1 and t1["median_runtime_ms"] == 5.5


def test_empty_plans_still_lists_every_template():
    out = aggregate([], TEMPLATES)
    assert len(out) == 2 and all(e["plans"] == 0 and e["top_ops"] == [] for e in out)
