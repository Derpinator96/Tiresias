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
