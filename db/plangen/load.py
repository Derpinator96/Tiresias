"""Load the plan-generation databases into pg-bench: dsb, tpch and quickmart (a smaller
QuickMart copy made by db/generate.py). Each is created once; --force reloads.

Raw generator output goes to BENCH_RAW_DIR (a Docker volume), never into the repo.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from common.config import cfg
from db import generate
from db.plangen import setups

DATABASES = ("dsb", "tpch", "quickmart")
BLOCK = 1 << 20


def dsn_for(database: str) -> str:
    return make_conninfo(os.environ["BENCH_DSN"], dbname=database)


def _ensure_database(name: str, force: bool) -> bool:
    """Create the database; return True if it must be (re)loaded."""
    with psycopg.connect(os.environ["BENCH_DSN"], autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if exists and not force:
            with psycopg.connect(dsn_for(name)) as db:
                loaded = db.execute("SELECT to_regclass('public.plangen_loaded') IS NOT NULL").fetchone()[0]
            if loaded:
                return False
        if exists:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return True


def _mark_loaded(conn, seconds: float) -> None:
    conn.execute("CREATE TABLE plangen_loaded (loaded_at timestamptz DEFAULT now(), seconds real)")
    conn.execute("INSERT INTO plangen_loaded (seconds) VALUES (%s)", (seconds,))


def _copy_file(conn, table: str, path: Path, strip_trailing_bar: bool, encoding: str | None) -> None:
    opts = "FORMAT csv, DELIMITER '|'" + (f", ENCODING '{encoding}'" if encoding else "")
    with conn.cursor().copy(f"COPY {table} FROM STDIN WITH ({opts})") as cp, open(path, "rb") as f:
        if strip_trailing_bar:
            for line in f:
                cp.write(line.rstrip(b"\r\n").removesuffix(b"|") + b"\n")
        else:
            while block := f.read(BLOCK):
                cp.write(block)


def load_dsb(force: bool = False, log=print) -> None:
    if not _ensure_database("dsb", force):
        log("dsb: already loaded")
        return
    t0 = time.perf_counter()
    home = Path(os.environ["DSB_HOME"])
    raw = Path(os.environ["BENCH_RAW_DIR"]) / "dsb"
    raw.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(home / "tools" / "dsdgen"), "-scale", str(cfg("plan_generation.dsb_scale_factor")),
                    "-dir", str(raw), "-terminate", "n", "-force"], cwd=home / "tools", check=True)
    with psycopg.connect(dsn_for("dsb"), autocommit=True) as conn:
        conn.execute((home / "scripts" / "create_tables.sql").read_text())
        tables = {r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()}
        for path in sorted(raw.glob("*.dat")):
            if path.stem in tables:
                log(f"dsb: loading {path.stem}")
                # TPC-DS text fields can hold Latin-1 bytes (UNVERIFIED for DSB; harmless if ASCII).
                _copy_file(conn, path.stem, path, strip_trailing_bar=False, encoding="LATIN1")
        conn.execute("ANALYZE")
        _mark_loaded(conn, time.perf_counter() - t0)
    log(f"dsb: loaded in {time.perf_counter() - t0:.0f} s")


def load_tpch(force: bool = False, log=print) -> None:
    if not _ensure_database("tpch", force):
        log("tpch: already loaded")
        return
    t0 = time.perf_counter()
    dbgen = Path(os.environ["TPCH_HOME"]) / "dbgen"
    raw = Path(os.environ["BENCH_RAW_DIR"]) / "tpch"
    raw.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DSS_CONFIG": str(dbgen), "DSS_PATH": str(raw)}
    subprocess.run([str(dbgen / "dbgen"), "-vf", "-s", str(cfg("plan_generation.tpch_scale_factor"))],
                   cwd=dbgen, env=env, check=True)
    with psycopg.connect(dsn_for("tpch"), autocommit=True) as conn:
        conn.execute((dbgen / "dss.ddl").read_text())
        for path in sorted(raw.glob("*.tbl")):
            log(f"tpch: loading {path.stem}")
            _copy_file(conn, path.stem, path, strip_trailing_bar=True, encoding=None)
        for stmt in setups.TPCH_PRIMARY_KEYS:
            conn.execute(stmt)
        conn.execute("ANALYZE")
        _mark_loaded(conn, time.perf_counter() - t0)
    log(f"tpch: loaded in {time.perf_counter() - t0:.0f} s")


def load_quickmart(force: bool = False, log=print) -> None:
    if not _ensure_database("quickmart", force):
        log("quickmart: already loaded")
        return
    t0 = time.perf_counter()
    timings = generate.load(dsn_for("quickmart"), int(cfg("plan_generation.quickmart_sales_rows")), log=log)
    with psycopg.connect(dsn_for("quickmart"), autocommit=True) as conn:
        _mark_loaded(conn, time.perf_counter() - t0)
    log(f"quickmart: loaded {timings}")


def load_all(force: bool = False, log=print) -> None:
    load_quickmart(force, log)
    load_tpch(force, log)
    load_dsb(force, log)
