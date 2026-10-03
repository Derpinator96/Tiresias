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


def test_mining_candidates_panel_shows_support(app):
    assert any(h.value == "Candidate indexes from mining" for h in app.header)
    rows = app.dataframe[-1].value.to_dict("records")
    q1 = [r for r in rows if r["candidate index"] == "sales (region_id, transaction_date)"]
    assert q1 and q1[0]["support"].endswith("%") and q1[0]["templates"] >= 1, rows


def test_drift_panel_shows_distance_and_trigger_state(app):
    assert any(h.value == "Workload drift" for h in app.header)
    labels = {m.label: m.value for m in app.metric}
    assert labels["Drift"] in ("triggered", "not triggered")
    assert labels["Current JS distance"] == "no two windows yet" or 0.0 <= float(labels["Current JS distance"]) <= 1.0
    next(b for b in app.button if b.label == "Check for drift").click().run()
    assert not app.exception, app.exception


def test_drift_trigger_reruns_the_search_with_the_new_mix(monkeypatch):
    """The live trigger is proven by miner/tests/test_drift_live.py; here ai's drift state is
    forced to triggered to check what the panel does with it."""
    real = data.ai
    sent = []

    def ai(path, body=None, method=None):
        r = real(path, body, method)
        if path == "/ai/mine":
            body_ = r.json()
            body_["drift"].update(triggered=True, triggered_at=1791000000)
            r.json = lambda: body_
        if path == "/ai/rl/run":
            sent.append(body)
        return r
    monkeypatch.setattr(data, "ai", ai)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    assert any(m.label == "Drift" and m.value == "triggered" for m in at.metric)
    assert sent and "weights" in sent[-1]
    text = text_of(at)
    assert "Drift triggered by the window ending" in text and "Q-table" in text
    assert "New recommendation: add index on" in text or any("no index worth" in i.value for i in at.info)


ADVERSARIAL = {  # shape written by privacy_tests/adversarial.py
    "window": {"since": "2026-10-03T10:00:00+00:00", "until": "2026-10-03T10:02:00+00:00"},
    "llm": {"provider": "gemini", "model": "m", "temperature": 0, "llm_payload_id": "pay_0000abcd", "guesses_returned": 4},
    "material": {"payloads_in_window": 9, "payloads_sent": 9, "chars_in_window": 1200, "chars_sent": 1200, "llm_payloads_sent": 2},
    "hashed": {"all": {"codes": 4, "exact": 1, "synonym": 1, "exact_rate": 0.25, "rate": 0.5},
               "table": {"codes": 1, "exact": 0, "synonym": 1, "exact_rate": 0.0, "rate": 1.0},
               "column": {"codes": 3, "exact": 1, "synonym": 0, "exact_rate": 0.3333, "rate": 0.3333}},
    "baseline_random_common_names": {"exact_rate": 0.02, "rate": 0.031, "table_names_listed": 40, "column_names_listed": 60},
    "plaintext_upper_bound": {"rate": 1.0, "assumption": "by construction"},
    "plaintext_llm_control": "pending air-gapped mode",
}


@pytest.mark.parametrize("result", [None, ADVERSARIAL])
def test_adversarial_panel_shows_score_baseline_and_label(monkeypatch, result):
    monkeypatch.setattr(data, "adversarial", lambda: result)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    assert data.LABELS["adversarial"] in text_of(at)
    metrics = {m.label: m.value for m in at.metric}
    if result is None:
        assert any("make adversarial" in i.value for i in at.info)
    else:
        assert metrics["Codes the adversary named from hashed payloads"] == "2 of 4 (50%)"
        assert metrics["Random common-name guess (expected)"] == "3.1%"
        assert metrics["Plaintext payloads (upper bound)"] == "100%"


def test_llm_in_use_is_named_on_screen(app):
    info = data.llm_info()
    assert info["label"].startswith("LLM: ") and info["label"] != data.LLM_UNKNOWN
    assert info["label"] in text_of(app)
