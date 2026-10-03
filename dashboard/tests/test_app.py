"""Dashboard tests. Run in the dashboard container (it reaches the gateway and ai):

    docker compose ... exec dashboard python -m pytest -p no:cacheprovider /app/dashboard/tests

Uses streamlit.testing.v1.AppTest (present in the pinned Streamlit 1.65.0).
"""
import json
import os
import re
import tomllib

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import data

HERE = os.path.dirname(__file__)
APP = os.path.join(HERE, "..", "app.py")
REAL = re.compile(r"\b(sales|region_id|transaction_date|amount|customers)\b")


def text_of(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [h.value for h in at.header]
    parts += [json.dumps(e.proto.spec) for e in at.get("graphviz_chart")]
    return "\n".join(parts)


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def test_every_simplified_component_is_labelled(app):
    text = text_of(app)
    # The estimator label names whichever estimator ai is serving (GNN or the baseline).
    for label in [data.estimator_label()] + [v for k, v in data.LABELS.items() if k != "estimator"]:
        assert label in text, label


def test_branding_deploy_button_and_menu_are_off():
    conf = tomllib.load(open(os.path.join(HERE, "..", ".streamlit", "config.toml"), "rb"))
    assert conf["client"]["toolbarMode"] == "minimal"
    assert conf["browser"]["gatherUsageStats"] is False
    assert conf["browser"]["serverAddress"] == "127.0.0.1"


def test_dba_view_shows_real_names_ai_view_shows_only_codes(app):
    assert REAL.search(text_of(app)), "DBA view should show real names"
    app.toggle[0].set_value(True).run()
    assert not app.exception
    hashed = text_of(app)
    assert not REAL.search(hashed), REAL.search(hashed)
    assert re.search(r"\bt_[0-9a-f]{8}\b", hashed)


def test_search_twin_and_negative_control_panels(app):
    app.button[1].click().run()                       # Run search
    assert any("Add index on sales (region_id, transaction_date)" in m.value.replace("**", "") for m in app.markdown)
    app.button[2].click().run()                       # Measure on twin
    labels = {m.label: m.value for m in app.metric}
    assert "Before (measured)" in labels and "After (measured)" in labels
    assert any("not production size" in m.value for m in app.markdown)
    assert any("TestedOnly" in m.value for m in app.markdown)
    app.button[3].click().run()                       # Run negative control
    assert any("canary hits" in e.value for e in app.error)


def test_plan_dot_points_child_to_parent_and_avoids_purple():
    plan = {"nodes": [{"node_id": 0, "parent_id": None, "op": "Aggregate", "est_rows": 1, "est_cost": 1, "width": 1},
                      {"node_id": 1, "parent_id": 0, "op": "Seq Scan", "relation": "t_00000001", "est_rows": 1, "est_cost": 1, "width": 1}]}
    dot = data.plan_dot(plan, {"nodes": [{"node_id": 0, "share": 0.1}, {"node_id": 1, "share": 0.9}]})
    assert "n1 -> n0;" in dot and "rankdir=BT" in dot
    for colour in re.findall(r'fillcolor="#([0-9a-f]{6})"', dot):
        r, g, b = (int(colour[i:i + 2], 16) for i in (0, 2, 4))
        assert r >= g == b       # grey to red only


def test_rewrite_panel_shows_each_checked_status_and_hides_real_sql_in_ai_view(app):
    next(b for b in app.button if b.label == "Verify rewrites").click().run()
    text = text_of(app)
    assert "date_trunc_eq_to_range" in text and "or_same_column_to_in" in text
    assert re.search(r"(Verified|TestedOnly|Rejected)\*\* \(VeriEQL: (pass|fail|unsupported|not_run), "
                     r"twin checksum: (match|mismatch|not_run)\)", text)
    assert any(REAL.search(c.value) for c in app.code), "DBA view should show the real rewritten SQL"
    app.toggle[0].set_value(True).run()
    assert not any(REAL.search(c.value) for c in app.code)


def test_search_lists_rewrites_and_every_configuration_rechecked_on_the_twin(app):
    next(b for b in app.button if b.label == "Run search").click().run()
    assert not app.exception, app.exception
    text = text_of(app).replace("**", "")
    # The Q2 rewrite is recommended with its honest check status, next to the Q1 index.
    assert "with rule date_trunc_eq_to_range (check: TestedOnly)" in text
    assert "Top configurations re-checked on the twin" in text
    assert "Final choice: best measured on the twin." in text
    assert text.count("Chosen. ") == 1
    assert re.search(r"measured drop -?\d+\.\d% \(median of \d+ runs per query", text)
    app.toggle[0].set_value(True).run()                 # AI view: codes only, rewrite included
    hashed = text_of(app)
    assert not REAL.search(hashed), REAL.search(hashed)
    assert re.search(r"Rewrite \*\*q_[0-9a-f]{8}\*\* with rule", hashed)


def test_twin_panel_shows_measured_write_cost(app):
    next(b for b in app.button if b.label == "Run search").click().run()
    next(b for b in app.button if b.label == "Measure on twin").click().run()
    assert not app.exception, app.exception
    added = {m.label: m.value for m in app.metric}["Insert latency added (measured)"]
    assert re.fullmatch(r"[+-]\d+\.\d{3} ms per insert", added), added
    assert any(data.LABELS["write_cost"] in m.value for m in app.markdown)


def test_plan_tree_defaults_to_the_slowest_and_is_selectable(app):
    box = next(s for s in app.selectbox if s.label == "Template (slowest first)")
    slow = data.gateway("/v1/templates/slow")
    assert box.value == 0 and box.options[0].startswith("1. ")       # the slowest, as before
    first = [json.dumps(e.proto.spec) for e in app.get("graphviz_chart")]
    other = next(i for i, t in enumerate(slow) if i and data.gateway(f"/v1/templates/{t['template_id']}/plans"))
    box.set_value(other).run()
    assert not app.exception
    assert [json.dumps(e.proto.spec) for e in app.get("graphviz_chart")] not in ([], first)


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_approve_panel_shows_three_files_in_dba_view_only(app):
    assert data.LABELS["approve_demo"] in text_of(app)
    assert not any(b.label == "Approve" for b in app.button)            # needs a search result first
    button(app, "Run search").click().run()
    button(app, "Verify rewrites").click().run()
    button(app, "Approve").click().run()
    assert not app.exception
    files = {e.label: e for e in app.expander}
    assert {"migration.sql", "rollback.sql", "post_deploy_check.py"} <= set(files)
    assert {d.label for d in app.download_button} >= {"Download migration.sql", "Download rollback.sql",
                                                       "Download post_deploy_check.py"}
    code = "\n".join(c.value for c in app.code)
    assert 'CREATE INDEX CONCURRENTLY "bt_sales_region_id_transaction_date" ON "sales" ("region_id", "transaction_date");' in code
    assert 'DROP INDEX CONCURRENTLY IF EXISTS "bt_sales_region_id_transaction_date";' in code
    kept = [k for k, rw in app.session_state["rewrites"].items() if rw["status"] != "Rejected"]
    assert kept and all(f"rewrite {rule} of template {tid}: a suggested application code change" in code for tid, rule in kept)

    button(app, "Run the post-deploy check on the twin").click().run()
    assert not app.exception
    text = text_of(app)
    assert re.search(r"Post-deploy check on the twin: \*\*(kept|rolled back)\*\*", text)
    assert "Ran on the twin with a shortened duration" in text
    assert re.search(r"median [0-9.]+ ms before \(\d+ runs\), [0-9.]+ ms after \(\d+ runs\), measured on the twin", text)

    app.toggle[0].set_value(True).run()                                  # AI view: no file, no real name
    assert not app.exception
    assert not any(d.label.startswith("Download ") for d in app.download_button)
    assert not any(e.label.endswith((".sql", ".py")) for e in app.expander)
    assert not any(REAL.search(c.value) for c in app.code)
    assert not REAL.search(text_of(app))
FIDELITY_DOC = {"queries": [{"query": "q2", "rewrite": "date_trunc_eq_to_range", "indexes": 1,
                             "twin": {"before_ms": 900.0, "after_ms": 300.0, "speedup": 3.0},
                             "production": {"before_ms": 1000.0, "after_ms": 250.0, "speedup": 4.0},
                             "fidelity": 0.75, "plan_agrees": {"before": True, "after": False}}]}


def test_fidelity_rows_show_config_names_only_in_the_dba_view():
    dba, = data.fidelity_rows(FIDELITY_DOC, names=True)
    ai, = data.fidelity_rows(FIDELITY_DOC, names=False)
    assert REAL.search(dba["configuration"]) and not REAL.search(ai["configuration"])
    assert dba["fidelity"] == 0.75 and dba["plans agree before / after"] == "yes / no"


def test_fidelity_panel_labels_its_assumptions(app):
    assert any(h.value.startswith("Twin fidelity") for h in app.header)
    assert any(data.LABELS["fidelity"] in c.value for c in app.caption)
    if not app.info or not any("make fidelity" in i.value for i in app.info):   # a make fidelity result exists
        table = app.dataframe[-1].value
        assert {"twin speedup", "pg-prod speedup", "fidelity"} <= set(table.columns)
        assert any("speedup = before ms / after ms" in m.value for m in app.markdown)
        app.toggle[0].set_value(True).run()
        assert not REAL.search(app.dataframe[-1].value.to_string())
