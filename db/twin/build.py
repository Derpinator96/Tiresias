"""Statistical twin builder (doc, Component 6 and Detailed component specs, Twin).

SIMPLIFIED: every column is generated independently from pg-prod's pg_stats. Column
correlations are not preserved yet (for example, a sale's region_id no longer matches its
store's region). On-screen label: LABEL below.

Runs on the private side (tools container). It reads pg_stats locally, including value
lists, but writes no real value into the twin:
- primary keys: 1..n;
- foreign keys: parent IDs by frequency rank. The k-th most common real value becomes twin
  ID k with the same frequency; the remaining mass is spread over the remaining parent IDs;
- numbers and dates: each most-common value is replaced by a value sampled between its
  neighbours in the sorted list of known values (so range selectivity stays close); the rest
  is sampled uniformly inside histogram buckets, one bucket at a time with equal weight
  (Postgres histograms are equi-depth);
- text: most-common values become synthetic strings of the same length; everything else is
  a synthetic string of about the column's average width. Text histograms are never used:
  they hold real values (in this database the first email bound is a planted canary);
- NULLs at each column's null fraction.

The frequency-rank map (real most-common value -> twin value) is written to a private file
(config sandbox.twin_map_path) so a replayed query's equality literals can be translated.
See db/NOTES.md for the mapping rule.

Table sizes: the hero table at sandbox.twin_hero_table_scale, others at
sandbox.twin_other_tables_scale, but never below the number of distinct values a child
table's foreign key needs (otherwise 12 regions would shrink to 2).

Tables are generated and copied in chunks of workload.copy_batch_rows.

TODO(correlations): for column pairs the miner flags, sample the second column from a
bucketed table conditioned on the first (doc, Twin).
"""
from __future__ import annotations

import io
import json
import os
from datetime import date

import numpy as np
import pandas as pd
import psycopg

from common.config import cfg

LABEL = "twin: synthetic from pg_stats, no column correlations yet"
NUMBER_TYPES = {"integer", "bigint", "smallint", "numeric", "real", "double precision"}
INT_TYPES = {"integer", "bigint", "smallint"}


def _read_stats(conn) -> dict:
    cols = conn.execute("""
        SELECT c.table_name, c.column_name, c.data_type, c.ordinal_position
        FROM information_schema.columns c
        JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position""").fetchall()
    stats = {(t, a): (nd, nf, w, mcv, mcf, hist) for t, a, nd, nf, w, mcv, mcf, hist in conn.execute("""
        SELECT tablename, attname, n_distinct, null_frac, avg_width,
               most_common_vals::text::text[], most_common_freqs, histogram_bounds::text::text[]
        FROM pg_stats WHERE schemaname = 'public'""")}
    keys = conn.execute("""
        SELECT con.conrelid::regclass::text, a.attname, con.contype, con.confrelid::regclass::text
        FROM pg_constraint con JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
        WHERE con.connamespace = 'public'::regnamespace AND con.contype IN ('p', 'f')""").fetchall()
    # Exact counts, not pg_class.reltuples: that is an estimate (10,000,220 for 10,000,000 sales
    # rows), and the hero table must match production exactly. One count(*) per table is cheap.
    names = [r[0] for r in conn.execute("""SELECT relname FROM pg_class
                                          WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'""")]
    rows = {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in names}
    tables: dict[str, list] = {}
    for t, a, typ, _ in cols:
        tables.setdefault(t, []).append((a, typ, stats.get((t, a))))
    pk = {(t, a) for t, a, k, _ in keys if k == "p"}
    fk = {(t, a): parent for t, a, k, parent in keys if k == "f"}
    return {"tables": tables, "pk": pk, "fk": fk, "rows": rows}


def _to_num(values: list[str], typ: str) -> np.ndarray:
    if typ == "date":
        return np.array([date.fromisoformat(v).toordinal() for v in values], dtype=float)
    return np.array([float(v) for v in values], dtype=float)


def _from_num(x: np.ndarray, typ: str):
    if typ == "date":
        return np.array([date.fromordinal(int(round(v))).isoformat() for v in x], dtype=object)
    if typ in INT_TYPES:
        return np.round(x).astype(np.int64)
    return np.round(x, 2)


def _target_rows(meta: dict) -> dict[str, int]:
    hero = "sales"   # the hero table holds Q1; the doc keeps it at full size
    out = {}
    for t, n in meta["rows"].items():
        scale = float(cfg("sandbox.twin_hero_table_scale")) if t == hero else float(cfg("sandbox.twin_other_tables_scale"))
        out[t] = max(1, round(n * scale))
    # A parent never shrinks below the distinct values its children's foreign keys need.
    for (child, col), parent in meta["fk"].items():
        st = dict((a, s) for a, _, s in meta["tables"][child])[col]
        if st:
            nd = st[0] if st[0] >= 0 else -st[0] * meta["rows"][child]
            out[parent] = max(out[parent], min(meta["rows"][parent], int(round(nd))))
    return out


def _column_sampler(rng, typ, stat, role, parent_n, colname):
    """Return (draw, mapping). draw(start, size) gives values for rows start .. start + size - 1;
    mapping = [[real, twin], ...] for most-common values. Synthetic most-common values are fixed
    here, once, so every chunk of a table uses the same ones."""
    nd, nf, width, mcv, mcf, hist = stat or (0, 0.0, 8, None, None, None)
    mcv, mcf, hist = list(mcv or []), list(mcf or []), list(hist or [])
    mapping: list[list] = []
    if role == "pk":
        return (lambda start, size: np.arange(start + 1, start + size + 1)), mapping

    if role == "fk":
        order = np.argsort(mcf)[::-1]
        k = min(len(order), parent_n)
        ids = np.arange(1, k + 1)
        probs = np.array([mcf[i] for i in order[:k]])
        mapping = [[mcv[i], int(j)] for i, j in zip(order[:k], ids)]
        cut = np.cumsum(probs) if k else None
        # The remaining mass goes to parent IDs no most-common value claimed; if every parent
        # is claimed, it is spread over all of them.
        others = np.arange(k + 1, parent_n + 1) if parent_n > k else np.arange(1, parent_n + 1)

        def draw_fk(start, size):
            draw = rng.random(size)
            out = np.empty(size, dtype=np.int64)
            in_mcv = np.zeros(size, dtype=bool)
            if k:
                in_mcv = draw < cut[-1]
                out[in_mcv] = ids[np.minimum(np.searchsorted(cut, draw[in_mcv], side="right"), k - 1)]
            out[~in_mcv] = rng.choice(others, int((~in_mcv).sum()))
            return out
        return draw_fk, mapping

    numeric = typ in NUMBER_TYPES or typ == "date"
    p_mcv = float(sum(mcf))
    if numeric:
        anchors = np.unique(np.concatenate([_to_num(mcv, typ), _to_num(hist, typ)])) if (mcv or hist) else np.array([0.0])
        synth = []
        for v in _to_num(mcv, typ):
            i = np.searchsorted(anchors, v)
            lo = anchors[i - 1] if i > 0 else v
            hi = anchors[i + 1] if i + 1 < len(anchors) else v
            synth.append(rng.uniform(lo, hi))
        synth_vals = _from_num(np.array(synth), typ) if synth else np.array([])
        mapping = [[m, s.item() if hasattr(s, "item") else s] for m, s in zip(mcv, synth_vals)]
        h = _to_num(hist, typ)
    else:
        synth_vals = [("v" + str(r + 1)).ljust(len(m), "x") for r, m in enumerate(mcv)]
        mapping = [[m, s] for m, s in zip(mcv, synth_vals)]
        w = max(4, int(width or 8))
    cut = np.cumsum(mcf) if mcv else None

    def draw(start, size):
        choice = rng.random(size)
        vals = np.empty(size, dtype=object)
        rest = choice >= p_mcv
        n_rest = int(rest.sum())
        if numeric:
            if len(h) >= 2:
                b = rng.integers(0, len(h) - 1, n_rest)
                hv = _from_num(rng.uniform(h[b], h[b + 1]), typ)
            else:
                hv = _from_num(np.full(n_rest, anchors[0]), typ)
            vals[rest] = list(hv)
        else:
            vals[rest] = [f"{colname[:2]}{x:0{w - 2}x}"[:max(w, 6)] for x in rng.integers(0, 16 ** min(w - 2, 12), n_rest)]
        if mcv:
            idx = np.searchsorted(cut, choice[~rest], side="right")
            vals[~rest] = [synth_vals[i] for i in idx]
        if nf > 0:
            vals[rng.random(size) < nf] = None
        return vals
    return draw, mapping


def build(prod_dsn: str, twin_dsn: str, log=print) -> dict:
    """Fill the twin table by table, parents first, in chunks of workload.copy_batch_rows so
    a 50,000,000-row hero table never sits in memory at once."""
    rng = np.random.default_rng(int(cfg("dataset.random_seed")) + 1)
    batch = int(cfg("workload.copy_batch_rows"))
    with psycopg.connect(prod_dsn) as conn:
        meta = _read_stats(conn)
    sizes = _target_rows(meta)
    # Parents before children.
    order, pending = [], set(meta["tables"])
    while pending:
        ready = sorted(t for t in pending if all(p in order or p == t for (c, _), p in meta["fk"].items() if c == t))
        order += ready
        pending -= set(ready)
    maps = {}
    with psycopg.connect(twin_dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(order) + " CASCADE")
        # Foreign keys stay declared (pg_dump copied them), but their per-row trigger checks are
        # skipped while loading: every generated foreign key is drawn from 1..parent rows, so it
        # is valid by construction. Needs a superuser, which the tools container connects as.
        conn.execute("SET session_replication_role = replica")
        for t in order:
            cols, samplers = [], []
            for col, typ, stat in meta["tables"][t]:
                role = "pk" if (t, col) in meta["pk"] else ("fk" if (t, col) in meta["fk"] else None)
                parent_n = sizes[meta["fk"][(t, col)]] if role == "fk" else 0
                draw, m = _column_sampler(rng, typ, stat, role, parent_n, col)
                cols.append(col)
                samplers.append(draw)
                if m:
                    maps[f"{t}.{col}"] = m
            for start in range(0, sizes[t], batch):
                size = min(batch, sizes[t] - start)
                frame = pd.DataFrame({c: d(start, size) for c, d in zip(cols, samplers)})
                buf = io.StringIO()
                frame.to_csv(buf, index=False, header=False)
                with conn.cursor().copy(f"COPY {t} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv)") as cp:
                    cp.write(buf.getvalue())
                done = start + size
                if done % (batch * 20) == 0 and done < sizes[t]:
                    log(f"twin {t}: {done:,} of {sizes[t]:,} rows")
        conn.execute("SET session_replication_role = DEFAULT")
        conn.execute("ANALYZE")
    path = cfg("sandbox.twin_map_path")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(maps, f)
    return {"rows": {t: sizes[t] for t in order}, "mapped_columns": len(maps)}


if __name__ == "__main__":
    print(build(os.environ["PROD_DSN"], os.environ["TWIN_DSN"]))
