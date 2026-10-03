"""Write cost on the twin (doc, Component 6 step 4): pgbench inserts sales rows at
sandbox.pgbench_insert_rate_per_s for sandbox.pgbench_duration_s, once without and once with a
configuration's indexes. Private side: real names, runs in the gateway, never in ai.

The gateway has no pgbench binary and no docker socket, so pgbench runs inside pg-twin itself:
the server starts it with COPY ... FROM PROGRAM (needs superuser, which the gateway already is
on the twin), pgbench connects over pg-twin's local socket, and its per-transaction log comes
back as the rows of that COPY. Flags and log format checked against pgbench 16.15
(`pgbench --help` in pg-twin, and its log output).

Each transaction is one INSERT that copies a twin row into a new sale with the next order_id.
Source rows are drawn from the first rate x duration rows, which stay cached, so the copy's read
is small and the same in both runs; new keys land where the twin's own (random) data puts them.
The number is the median per-insert latency: on a busy machine the mean is dominated by a few
scheduling stalls (measured 2026-10-03, db/NOTES.md). pgbench's session runs with
synchronous_commit off, so commits do not wait for the WAL flush and the target rate holds; that
flush wait is not part of the number. Afterwards the inserted rows are deleted and sales is
vacuumed, so the twin keeps its rows.
"""
from __future__ import annotations

import shlex
import statistics

import psycopg
from psycopg import sql

from common.config import cfg

RATE = int(cfg("sandbox.pgbench_insert_rate_per_s"))
DURATION_S = int(cfg("sandbox.pgbench_duration_s"))
LABEL = (f"write cost: pgbench on the twin, {RATE} inserts/s for {DURATION_S} s, median INSERT latency "
         "with minus without the indexes (WAL flush wait excluded)")

# :id starts at the twin's largest order_id (-D); pgbench keeps a client's variables between
# transactions, so `\set id :id + 1` numbers the new rows.
SCRIPT = r"""\set src random(1, :k)
\set id :id + 1
INSERT INTO sales SELECT :id, customer_id, product_id, store_id, region_id, transaction_date, quantity, amount, payment_method FROM sales WHERE order_id >= :src ORDER BY order_id LIMIT 1;
"""


def median_ms(log: list[str]) -> float:
    """pgbench -l with -R writes one line per transaction: client_id transaction_no time
    script_no time_epoch time_us schedule_lag, times in microseconds. `time` counts from the
    scheduled start, so the insert's own latency is time minus schedule_lag."""
    return statistics.median(int(f[2]) - int(f[6]) for f in map(str.split, log)) / 1000


def insert_ms(conn: psycopg.Connection) -> float:
    """Run the insert workload on the twin `conn` points at (autocommit, superuser) and return
    the median INSERT latency in ms. The inserted rows are removed even if pgbench fails."""
    n = int(conn.execute("SELECT max(order_id) FROM sales").fetchone()[0])
    log = "/tmp/bt_pgbench_$$"     # pg-twin's /tmp; $$ is this shell's pid
    program = (f"PGOPTIONS='-c synchronous_commit=off' pgbench -n -M prepared -R {RATE} -T {DURATION_S}"
               f" --random-seed={int(cfg('dataset.random_seed'))} -l --log-prefix={log}"
               f" -D k={min(n, RATE * DURATION_S)} -D id={n} -f - {shlex.quote(conn.info.dbname)} >/dev/null <<'EOF'\n"
               f"{SCRIPT}EOF\ns=$?; cat {log}.*; rm -f {log}.*; exit $s")
    try:
        with conn.transaction():
            conn.execute("CREATE TEMP TABLE bt_pgbench_log (line text) ON COMMIT DROP")
            conn.execute(sql.SQL("COPY bt_pgbench_log FROM PROGRAM {}").format(sql.Literal(program)))
            log_lines = [r[0] for r in conn.execute("SELECT line FROM bt_pgbench_log")]
    finally:
        with conn.transaction():
            # Skips the foreign key trigger from returns, which would scan returns per deleted row;
            # no return can point at a row pgbench just made.
            conn.execute("SET LOCAL session_replication_role = replica")
            conn.execute("DELETE FROM sales WHERE order_id > %s", (n,))
        conn.execute("VACUUM sales")
    return median_ms(log_lines)
