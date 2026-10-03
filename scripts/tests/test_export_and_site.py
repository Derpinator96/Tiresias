"""Tests for the results exporter and the public site build (tools container; no services needed)."""
import importlib.util
import os
import json
import re

import pytest

from common.config import REPO_ROOT
from db import canaries
from scripts import export_results, public_names

spec = importlib.util.spec_from_file_location("site_build", REPO_ROOT / "site" / "build.py")
site_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_build)

RUN = {
    "run_id": "run_0000beef", "finished_at": "2026-10-03T12:00:00Z", "elapsed_s": 40.0,
    "dataset": {"hero_table_rows": 1000000, "hero_table_size_mb": 95.0},
    "q1": {"mean_ms_before": 28.6, "slow_threshold_ms": 10},
    "twin": {"before_ms": 24.297, "after_ms": 2.662, "speedup_pct": 89.0, "storage_mb": 6.8, "runs": 5, "checksum_match": True},
    "search": {"label": "search: greedy (RL pending)", "predicted_before_ms": 28.573, "predicted_after_ms": 10.253,
               "estimator_label": "estimator: Postgres cost x calibration (GNN pending)", "recommended_columns": 2},
    "privacy": {"payloads": 30, "llm_payloads": 6, "canary_hits": 0, "canaries_planted": 20},
    "llm": {"provider": "gemini", "model": "gemini-3.8-flash", "tool_calls": 5, "numbers_checked": 4},
}
# QuickMart's real identifiers: none may appear on the public site (list in scripts/public_names.py).
REAL = public_names.REAL


@pytest.fixture
def built(tmp_path, monkeypatch):
    def run(results: dict | None):
        dist = tmp_path / "dist"
        res = tmp_path / "results.json"
        if results is not None:
            res.write_text(json.dumps(results), encoding="utf-8")
        monkeypatch.setattr(site_build, "DIST", dist)
        monkeypatch.setattr(site_build, "RESULTS", res)
        site_build.build()
        return {p.name: p.read_text(encoding="utf-8") for p in dist.iterdir() if p.suffix in (".html", ".svg", ".css", ".json")}
    return run


def test_git_commit_is_a_full_hash():
    assert re.fullmatch(r"[0-9a-f]{40}", export_results.git_commit())


def test_export_refuses_without_a_passing_run(tmp_path, monkeypatch):
    monkeypatch.setattr(export_results, "RUN", tmp_path / "missing.json")
    monkeypatch.setattr(export_results, "OUT", tmp_path / "results.json")
    assert export_results.main() == 1
    assert not (tmp_path / "results.json").exists()


def test_export_carries_run_id_time_size_commit_and_assumptions():
    out = export_results.build(RUN, "a" * 40)
    assert out["run_id"] == "run_0000beef" and out["finished_at"] and out["git_commit"] == "a" * 40
    assert out["dataset"]["hero_table_rows"] == 1000000
    for r in out["results"]:
        assert r["source"] and r["assumption"], r["name"]
    values = {r["name"]: r["value"] for r in out["results"]}
    assert values["Hero query after the recommended index"] == 2.662 and values["Canary hits in those payloads"] == 0


def test_all_five_pages_and_favicon_exist(built):
    files = built(None)
    for page in ("index.html", "architecture.html", "results.html", "privacy.html", "terms.html", "favicon.svg"):
        assert page in files
    for name, body in files.items():
        if name.endswith(".html"):
            assert 'rel="icon" href="/favicon.svg"' in body
            assert 'href="/privacy.html"' in body and 'href="/terms.html"' in body


def test_results_page_without_run_is_a_labelled_placeholder(built):
    page = built(None)["results.html"]
    assert "PLACEHOLDER" in page
    assert not re.search(r"\d+(\.\d+)?\s*(ms|MB|%)", page)


def test_results_page_renders_only_results_json(built):
    results = export_results.build(RUN, "b" * 40)
    page = built(results)["results.html"]
    assert "run_0000beef" in page and "bbbbbbbbbbbb" in page and "2026-10-03T12:00:00Z" in page
    body = page.split("<main>", 1)[1].split("</main>", 1)[0]
    allowed = json.dumps(results)
    for n in re.findall(r"(?<![\w.#-])\d[\d,]*(?:\.\d+)?", re.sub(r"<[^>]+>", " ", body)):
        assert n.replace(",", "") in allowed.replace(",", "") or n in allowed, n
    assert "not production size" in page


def test_no_real_names_canaries_or_em_dashes(built):
    files = built(export_results.build(RUN, "c" * 40))
    for name, body in files.items():
        text = re.sub(r"<[^>]+>", " ", body).lower() if name.endswith(".html") else body.lower()
        for real in REAL:
            assert not re.search(rf"\b{real}\b", text), (name, real)
        for c in canaries.ALL:
            assert c.value.lower() not in text, (name, c.kind)
        assert chr(0x2014) not in body and chr(0x2013) not in body, name   # em dash, en dash


def test_no_builder_badge_or_external_scripts(built):
    for name, body in built(None).items():
        if name.endswith(".html"):
            assert "<script" not in body
            assert not re.search(r"made with|built with|powered by", body, re.I), name


# ---- site/web (Next.js), the public deploy since 2026-10-04 ------------------------------------
# Scans `npm run build` output of a public build (NEXT_PUBLIC_BT_LOCAL unset). make test-web builds
# it in a node container first and sets BT_REQUIRE_WEB_BUILD=1 so a missing build fails.
WEB = REPO_ROOT / "site" / "web"
NEXT = WEB / ".next"
web = pytest.mark.skipif(not (NEXT / "BUILD_ID").exists() and os.environ.get("BT_REQUIRE_WEB_BUILD") != "1",
                         reason="site/web is not built (npm run build)")
STAGES = ["source", "gateway", "miner", "gnn", "rl", "llm", "twin", "dba"]   # src/lib/store.ts STAGES
PUBLIC_ROUTES = {"/", "/playground", "/ask", "/hashing", "/privacy", "/terms", *(f"/stages/{s}" for s in STAGES)}
SNAKE = [r for r in REAL if "_" in r] + ["quickmart"]   # plain English words also occur in minified libraries


def _server_files():
    app = NEXT / "server" / "app"
    return [p for p in app.rglob("*") if p.is_file() and (p.suffix in (".html", ".rsc", ".body") or ".segments" in str(p))]


def _own_source():
    src = WEB / "src"
    return [p for p in src.rglob("*") if p.is_file() and "components/ui" not in p.as_posix()
            and p.suffix in (".ts", ".tsx", ".css", ".json", ".svg")]


def _scan(path, words):
    body = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", body).lower() if path.suffix == ".html" else body.lower()
    for real in words:
        assert not re.search(rf"\b{real}\b", text), (str(path.relative_to(WEB)), real)
    for c in canaries.ALL:
        assert c.value.lower() not in text, (str(path.relative_to(WEB)), c.kind)
    assert chr(0x2014) not in body and chr(0x2013) not in body, str(path.relative_to(WEB))
    assert not re.search(r"made with|built with|powered by", text), str(path.relative_to(WEB))


@web
def test_web_pages_and_own_source_have_no_real_names_canaries_dashes_or_badges():
    files = _server_files() + _own_source()
    assert files
    for p in files:
        _scan(p, REAL)


@web
def test_web_client_chunks_have_no_names_canaries_or_live_ask_path():
    chunks = [p for p in (NEXT / "static").rglob("*") if p.suffix in (".js", ".css")]
    assert chunks
    for p in chunks:
        body = p.read_text(encoding="utf-8", errors="replace")
        for real in SNAKE:
            assert not re.search(rf"\b{real}\b", body.lower()), (p.name, real)
        for c in canaries.ALL:
            assert c.value.lower() not in body.lower(), (p.name, c.kind)
        assert "/api/ask" not in body, (p.name, "live Ask code in a public build")


@web
def test_web_pages_link_icon_privacy_and_terms():
    pages = [p for p in (NEXT / "server" / "app").rglob("*.html") if not p.name.startswith("_global-error")]
    assert pages
    for p in pages:
        body = p.read_text(encoding="utf-8")
        assert 'rel="icon"' in body and 'href="/privacy"' in body and 'href="/terms"' in body, p.name
        for src in re.findall(r'<script[^>]*\ssrc="([^"]+)"', body):
            assert src.startswith("/_next/"), (p.name, src)


@web
def test_web_prerenders_every_public_route_and_no_api():
    routes = set(json.loads((NEXT / "prerender-manifest.json").read_text(encoding="utf-8"))["routes"])
    assert PUBLIC_ROUTES <= routes, PUBLIC_ROUTES - routes
    assert not [r for r in routes if r.startswith("/api")]
