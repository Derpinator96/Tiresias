"""Scenario (doc acceptance, Gateway and privacy): unparsable SQL is withheld and logged, never
sent raw. No LLM call. Run in the tools container after make up and make seed (make e2e-offline).

The application role runs one statement the gateway's sqlglot cannot parse: Postgres's text
pattern operator ~>=~, with a canary comment, canary literals and a pg_sleep that makes it slow,
so auto_explain logs it with its literals and it would rank as a slow template if it parsed.
Then the AI-facing reads that would carry it run through the real gateway and ai. Asserts:
the gateway lists its queryid as withheld (reason only, no text); no payload ledgered during the
test holds its text, its operator or any canary; zero canary hits and no blocked payload.
"""
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import psycopg

from common.config import cfg
from db import canaries, run_q1
from e2e.test_q1 import AI, gw
from gateway.canary_scan import Scanner

OPERATOR = "~>=~"     # text pattern operator: valid Postgres, a ParseError in sqlglot 30.21.0


def test_unparsable_query_is_withheld_and_logged():
    started, run_started = time.time(), datetime.now(timezone.utc)
    pause_s = 1.5 * float(cfg("workload.slow_query_ms")) / 1000      # slow enough to be logged
    comment, email, name = canaries.COMMENTS[0].value, canaries.EMAILS[0].value, canaries.NAMES[0].value
    query = (f"/* {comment} */ SELECT count(*), pg_sleep({pause_s}) FROM customers "
             f"WHERE email {OPERATOR} '{email}' AND full_name ~<~ '{name}'")
    with psycopg.connect(run_q1.app_dsn(os.environ["PROD_DSN"]), autocommit=True) as conn:
        conn.execute(query).fetchall()
    with psycopg.connect(os.environ["PROD_DSN"], autocommit=True) as conn:
        rows = conn.execute("SELECT queryid, query, mean_exec_time FROM pg_stat_statements WHERE query LIKE %s",
                            (f"%{OPERATOR}%",)).fetchall()
    assert len(rows) == 1, rows
    queryid, stored_text, mean_ms = rows[0]
    assert comment in stored_text                      # the text the gateway reads holds a canary
    assert mean_ms >= cfg("workload.slow_query_ms")    # it would be a slow template if it parsed

    # Every AI-facing read that would carry a slow template, through the real services.
    slow = gw("/v1/templates/slow")
    for t in slow:
        gw(f"/v1/templates/{t['template_id']}/plans")
    gw("/v1/meta/columns")
    gw("/v1/workload/windows")
    r = httpx.post(AI + "/ai/mine", json={}, timeout=300)
    r.raise_for_status()

    # Withheld and logged by the gateway: the queryid and a reason, never the text.
    withheld = {w["queryid"]: w for w in gw("/v1/withheld")}
    assert queryid in withheld, "the gateway did not log the unparsable statement"
    assert withheld[queryid]["reason"].startswith("parse failed")
    assert OPERATOR not in json.dumps(withheld) and comment not in json.dumps(withheld)

    # Never sent raw: no payload of this test holds its text or any canary.
    until = datetime.now(timezone.utc)
    bodies = gw("/v1/ledger/payloads?" + urlencode({"since": run_started.isoformat(), "until": until.isoformat()}))["payloads"]
    assert bodies, "no payloads were ledgered"
    scanner = Scanner()
    for p in bodies:
        body = p["body"]
        assert OPERATOR not in body and stored_text not in body, p["payload_id"]
        assert scanner.scan(body) == [], p["payload_id"]
    entries = [e for e in gw("/v1/ledger")["entries"] if e["destination"] in ("ai", "llm")
               and run_started <= datetime.fromisoformat(e["time"].replace("Z", "+00:00")) <= until]
    assert entries and all(e["verdict"] == "allow" and not e["canary_hits"] for e in entries)

    elapsed = time.time() - started
    print(f"unparsable scenario: {len(bodies)} payloads checked, {elapsed:.1f} s")
    assert elapsed < cfg("tests.fast_suite_limit_s"), f"took {elapsed:.0f} s"
