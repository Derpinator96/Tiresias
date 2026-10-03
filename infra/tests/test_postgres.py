"""Run in the `tools` container. Checks the Postgres images: extensions loaded on pg-prod,
HypoPG on both, auto_explain absent on the twin (it would slow timed runs)."""
import os

import psycopg
import pytest


def _q(dsn_env, sql):
    with psycopg.connect(os.environ[dsn_env], autocommit=True) as conn:
        return conn.execute(sql).fetchall()


def test_server_is_postgres_16():
    for env in ("PROD_DSN", "TWIN_DSN"):
        (v,), = _q(env, "SHOW server_version_num")
        assert v.startswith("16"), (env, v)


def test_prod_preloads_stat_statements_and_auto_explain():
    (libs,), = _q("PROD_DSN", "SHOW shared_preload_libraries")
    assert {"pg_stat_statements", "auto_explain"} <= {x.strip() for x in libs.split(",")}


def test_twin_does_not_preload_auto_explain():
    (libs,), = _q("TWIN_DSN", "SHOW shared_preload_libraries")
    assert "auto_explain" not in libs


@pytest.mark.parametrize("env", ["PROD_DSN", "TWIN_DSN"])
def test_extensions_installed(env):
    names = {r[0] for r in _q(env, "SELECT extname FROM pg_extension")}
    assert {"pg_stat_statements", "hypopg"} <= names


@pytest.mark.parametrize("env", ["PROD_DSN", "TWIN_DSN"])
def test_hypopg_changes_the_plan(env):
    # One connection: hypothetical indexes live only in the session that made them.
    with psycopg.connect(os.environ[env], autocommit=True) as conn:
        conn.execute("CREATE TEMP TABLE hypo_probe AS SELECT g AS id FROM generate_series(1, 100000) g")
        conn.execute("ANALYZE hypo_probe")
        before = conn.execute("EXPLAIN SELECT * FROM hypo_probe WHERE id = 5").fetchall()
        conn.execute("SELECT * FROM hypopg_create_index('CREATE INDEX ON hypo_probe (id)')")
        after = conn.execute("EXPLAIN SELECT * FROM hypo_probe WHERE id = 5").fetchall()
    assert "Seq Scan" in before[0][0]
    assert "Index" in after[0][0] and "hypo" in after[0][0]


def test_auto_explain_log_is_json_lines():
    (dest,), = _q("PROD_DSN", "SHOW log_destination")
    assert dest == "jsonlog"
    assert os.path.isdir(os.environ["PGLOG_DIR"])
