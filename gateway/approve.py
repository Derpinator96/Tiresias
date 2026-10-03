"""Approve (doc, Component 8 and Detailed component specs, "Approve and deploy"): turn a Config
into migration.sql, rollback.sql and post_deploy_check.py, in real names.

Private side only. The files hold real table, column and index names and real logged queries
with their values, so they go to the operator dashboard only: never through send_to_ai, never
ledgered, never to ai. Nothing here changes pg-prod; it only reads the catalog
(pg_get_indexdef). The DBA runs the files.

twin_check runs the same files on pg-twin with a short replay, for the demo (LABEL).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import psycopg
import sqlglot
from sqlglot import exp

from common.config import cfg
from gateway import post_deploy_check as pdc

LABEL = (f"post-deploy check demo: runs on the twin with a shortened replay of {cfg('approve.demo_check_minutes')} "
         f"minutes per phase (production: {cfg('approve.post_deploy_check_minutes')} minutes)")
RUN = "Run with: psql -v ON_ERROR_STOP=1 -f {}  (no BEGIN/COMMIT and no --single-transaction: CONCURRENTLY cannot run in a transaction block)"


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def commented(text: str, prefix: str = "--      ") -> list[str]:
    return [prefix + line for line in text.splitlines()]


def index_name(table: str, cols: list[str]) -> str:
    # ponytail: plain cut at Postgres's 63-byte limit; two long names sharing a prefix would clash (CREATE fails loudly).
    return f"bt_{table}_{'_'.join(cols)}"[:63]


def _indexdef(dsn: str, name: str) -> tuple[str, bool]:
    """(pg_get_indexdef, whether a constraint owns the index). Catalog read only."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("""
            SELECT pg_get_indexdef(c.oid), EXISTS (SELECT 1 FROM pg_constraint WHERE conindid = c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'i' AND c.relname = %s""", (name,)).fetchone()
    if row is None:
        raise KeyError(name)
    return row


def _partition_steps(table: str, col: str) -> tuple[list[str], list[str]]:
    t, c, new, old = q(table), q(col), q(table + "_partitioned"), q(table + "_old")
    mig = [
        "--    Manual steps, not run by this file. Rewrites the whole table: plan a window with writes paused, rehearse on a copy.",
        f"--    a. CREATE TABLE {new} (LIKE {t} INCLUDING DEFAULTS INCLUDING CONSTRAINTS) PARTITION BY RANGE ({c});",
        "--    b. One partition per month of data, plus a default (placeholders in angle brackets):",
        f"--       CREATE TABLE {q(table + '_p<YYYY_MM>')} PARTITION OF {new} FOR VALUES FROM ('<YYYY-MM-01>') TO ('<first day of the next month>');",
        f"--       CREATE TABLE {q(table + '_pdefault')} PARTITION OF {new} DEFAULT;",
        f"--    c. A primary key or unique index on {new} must include {c}. Foreign keys that reference {t} must be dropped or re-pointed.",
        f"--    d. Copy the rows month by month (INSERT INTO {new} SELECT * FROM {t} WHERE {c} >= ... AND {c} < ...), recreate the other indexes, ANALYZE {new}.",
        f"--    e. In one short transaction: ALTER TABLE {t} RENAME TO {old}; ALTER TABLE {new} RENAME TO {t};",
    ]
    rb = [f"--    Manual: while {old} exists, copy rows written since the swap into it, then in one transaction rename {t} back to {new} and {old} to {t}."]
    return mig, rb


def build(g, snap, config: dict, replay_query: Callable[[str], str] = lambda s: s) -> dict[str, str]:
    """The three files for `config`. g is the Gateway, snap its Snapshot. replay_query maps each
    replayed query (the twin demo translates values to the twin's). Unknown codes raise
    KeyError; actions that cannot be undone or applied raise ValueError."""
    vault = g.hasher.vault
    index_codes = {g.hasher.index(name): name for name in snap.catalog.indexes}
    rewritten = g.rewritten_queries(snap, config)          # ValueError if a rule does not fit
    cid = config["config_id"]
    mig = [f"-- Blind Tuner migration for {cid} (search: {config['search']}).", "-- " + RUN.format("migration.sql"),
           "-- Before it: python post_deploy_check.py baseline. After it: python post_deploy_check.py check."]
    undo: list[list[str]] = []
    tables: set[str] = set()
    for n, a in enumerate(config["actions"], 1):
        if a["type"] == "add_index":
            [(table, cols)] = g.decode_config({"actions": [a]})
            name = index_name(table, cols)
            mig += [f"-- {n}. add_index on {table} ({', '.join(cols)})",
                    f"CREATE INDEX CONCURRENTLY {q(name)} ON {q(table)} ({', '.join(map(q, cols))});"]
            undo.append([f"-- undo {n}: drop the index migration.sql created (IF EXISTS: also clears an invalid index a failed build left)",
                         f"DROP INDEX CONCURRENTLY IF EXISTS {q(name)};"])
            tables.add(table)
        elif a["type"] == "drop_index":
            name = index_codes[a["index"]]
            definition, owned = _indexdef(g.prod_dsn, name)
            if owned:
                raise ValueError(f"index {name} belongs to a constraint; drop the constraint instead")
            table = snap.catalog.indexes[name][0]
            mig += [f"-- {n}. drop_index {name} on {table}", f"DROP INDEX CONCURRENTLY {q(name)};"]
            undo.append([f"-- undo {n}: recreate {name} from its definition on pg-prod (pg_get_indexdef)",
                         re.sub(r"^CREATE (UNIQUE )?INDEX ", r"CREATE \1INDEX CONCURRENTLY ", definition) + ";"])
            tables.add(table)
        elif a["type"] == "rewrite":
            tid, rule = a["template_id"], a["rule_id"]
            original = g.sample_queries(snap, [tid])[tid][0]
            mig += [f"-- {n}. rewrite {rule} of template {tid}: a suggested application code change, not run by this file.",
                    "--    Ship it only if the dashboard's Rewrites panel shows Verified or TestedOnly for it.",
                    "--    Original (latest logged query):", *commented(original),
                    "--    Rewritten:", *commented(rewritten[tid])]
            undo.append([f"-- undo {n}: revert the application code change, if it shipped. Nothing to run here."])
        else:   # partition
            table = vault[a["table"]]["name"]
            t, col = vault[a["column"]]["name"].split(".", 1)
            if t != table:
                raise ValueError("the partition column must belong to the partitioned table")
            steps, back = _partition_steps(table, col)
            mig += [f"-- {n}. partition {table} by month on {col} ({a['scheme']})", *steps]
            undo.append([f"-- undo {n}:", *back])
    rollback = [f"-- Blind Tuner rollback for {cid}: undoes migration.sql, last action first.", "-- " + RUN.format("rollback.sql"),
                "-- post_deploy_check.py check runs this file itself when a template's median latency gets worse."]
    for block in reversed(undo):
        rollback += block

    # Replay the slow templates that read a table an index action touches. Only templates with
    # a logged query can run; a generic $n plan cannot.
    slow = [t["template_id"] for t in g.slow_templates(snap)]
    queries = {tid: replay_query(s) for tid, (s, generic) in g.sample_queries(snap, slow).items()
               if not generic and tables & {x.name for x in sqlglot.parse_one(s, read="postgres").find_all(exp.Table)}}
    params = {"config_id": cid, "minutes": cfg("approve.post_deploy_check_minutes"),
              "worse_by": cfg("approve.rollback_if_median_worse_by"), "warmup_runs": cfg("sandbox.warmup_runs"),
              "queries": queries}
    src = Path(pdc.__file__).read_text(encoding="utf-8")
    check, hits = re.subn(r"^PARAMS = .*$", lambda _: "PARAMS = " + json.dumps(params, indent=1), src, count=1, flags=re.M)
    assert hits == 1, "post_deploy_check.py lost its PARAMS line"
    return {"migration.sql": "\n".join(mig) + "\n", "rollback.sql": "\n".join(rollback) + "\n", "post_deploy_check.py": check}


def twin_check(g, snap, config: dict, twin_dsn: str) -> dict:
    """Demo on pg-twin, never pg-prod: baseline, migration.sql, check (which runs rollback.sql if
    a template got worse), then rollback.sql if the check kept the change, so the twin returns
    to its baseline. Replays approve.demo_check_minutes per phase (LABEL)."""
    from db.sandbox import twin_measure
    mapping = twin_measure.load_map()
    files = build(g, snap, config, lambda s: twin_measure.map_query(s, mapping))
    minutes = cfg("approve.demo_check_minutes")
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            (Path(d) / name).write_text(text, encoding="utf-8")

        def phase(name: str) -> dict:
            r = subprocess.run([sys.executable, str(Path(d) / "post_deploy_check.py"), name, "--minutes", str(minutes)],
                               env={**os.environ, "BT_DSN": twin_dsn}, capture_output=True, text=True, check=True)
            return json.loads(r.stdout)

        base = phase("baseline")
        with psycopg.connect(twin_dsn, autocommit=True) as conn:
            pdc.run_sql(conn, files["migration.sql"])
        out = phase("check")
        if not out["rolled_back"]:
            with psycopg.connect(twin_dsn, autocommit=True) as conn:
                pdc.run_sql(conn, files["rollback.sql"])
    return {"ran_on": "twin", "minutes": minutes, "baseline": base["templates"], "templates": out["templates"],
            "worse": out["worse"], "worse_by": out["worse_by"], "rolled_back": out["rolled_back"]}
