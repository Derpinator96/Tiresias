"""Statistical twin builder (doc, Component 6 and Detailed component specs, Twin).

SIMPLIFIED: every column is generated from pg-prod's pg_stats, independently, except the
column pairs the miner flags (doc: "for column pairs the miner flags, sample the second
column from a local bucketed table conditioned on the first"). Correlations the miner does
not flag are lost, for example a sale's region_id against its store's region, or a return's
date against its sale's date. On-screen label: LABEL below.

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

Correlations (flagged_pairs, _joint, _conditional_u):
- pairs: adjacent columns of each candidate the miner returns (ai /ai/mine, hashed codes),
  translated back to names through the gateway's dehash on the private side. A pair whose
  second column is a primary key is flipped: a key cannot be resampled, the other column can;
- bucketed table: rows of prod counted by (first column's bucket, second column's bucket),
  computed in pg-prod; only counts leave the query. The first column is bucketed by its
  most-common values (the values the twin maps by frequency rank), the rest is one bucket. For
  a primary key, the twin ID k stands for the parent of rank k in the child's foreign key, so
  that child's most-common values are the buckets. The second column is bucketed exactly as its
  own sampler draws: most-common value, histogram bucket, or the rest;
- sampling: every sampler draws from one uniform u; each bucket owns an interval of u. For a
  flagged pair the bucket of the second column is drawn from the bucketed table given the
  first column's bucket, and u is placed inside that bucket's interval, so values stay
  synthetic (the same mapping and histogram sampling as an unflagged column).
"""
from __future__ import annotations

import io
import json
import os
from datetime import date

import httpx
import numpy as np
import pandas as pd
import psycopg
from psycopg import sql

from common.config import cfg

LABEL = "twin: synthetic from pg_stats, correlations kept only for column pairs the miner flags"
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
    """Return (draw, mapping). draw(start, size, u=None) gives values for rows start .. start +
    size - 1 from one uniform u per row (drawn here unless given); mapping = [[real, twin], ...]
    for most-common values. Synthetic most-common values are fixed here, once, so every chunk of
    a table uses the same ones. draw.intervals = {bucket: (lo, hi)}: the part of u each bucket
    owns ("m:<real most-common value>", "h:<histogram bucket 1..n>", "r" for the rest), so a
    conditional sampler can choose the bucket (module docstring, Correlations)."""
    nd, nf, width, mcv, mcf, hist = stat or (0, 0.0, 8, None, None, None)
    mcv, mcf, hist = list(mcv or []), list(mcf or []), list(hist or [])
    mapping: list[list] = []
    if role == "pk":
        draw_pk = lambda start, size, u=None: np.arange(start + 1, start + size + 1)
        draw_pk.intervals = {}
        return draw_pk, mapping

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
        edges = np.concatenate([[0.0], cut]) if k else np.array([0.0])
        intervals = {f"m:{mcv[i]}": (edges[j], edges[j + 1]) for j, i in enumerate(order[:k])}
        intervals["r"] = (edges[-1], 1.0)

        def draw_fk(start, size, u=None):
            draw = rng.random(size) if u is None else u
            out = np.empty(size, dtype=np.int64)
            in_mcv = np.zeros(size, dtype=bool)
            if k:
                in_mcv = draw < cut[-1]
                out[in_mcv] = ids[np.minimum(np.searchsorted(cut, draw[in_mcv], side="right"), k - 1)]
            out[~in_mcv] = rng.choice(others, int((~in_mcv).sum()))
            return out
        draw_fk.intervals = intervals
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
    edges = np.concatenate([[0.0], np.cumsum(mcf)])
    intervals = {f"m:{m}": (edges[i], edges[i + 1]) for i, m in enumerate(mcv)}
    n_buckets = len(h) - 1 if numeric and len(h) >= 2 else 0
    rest_mass = max(1.0 - p_mcv, 1e-12)
    if n_buckets:
        # Equi-depth histogram: the rest of u splits into equal parts, one per bucket.
        step = rest_mass / n_buckets
        intervals.update({f"h:{j + 1}": (p_mcv + j * step, p_mcv + (j + 1) * step) for j in range(n_buckets)})
    else:
        intervals["r"] = (p_mcv, 1.0)

    def draw(start, size, u=None):
        choice = rng.random(size) if u is None else u
        vals = np.empty(size, dtype=object)
        rest = choice >= p_mcv
        n_rest = int(rest.sum())
        if numeric:
            if n_buckets:
                b = np.minimum(((choice[rest] - p_mcv) / rest_mass * n_buckets).astype(np.int64), n_buckets - 1)
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
    draw.intervals = intervals
    return draw, mapping


def flagged_pairs() -> list[tuple[str, str, str]]:
    """(table, first, second) for adjacent columns of every miner candidate, best candidate
    first. The miner runs on the AI side on hashed codes (ai /ai/mine); the private side
    translates the codes through the gateway's dehash, as the dashboard does."""
    r = httpx.post(os.environ["AI_URL"].rstrip("/") + "/ai/mine", timeout=300)
    r.raise_for_status()
    cands = r.json()["candidates"]
    codes = sorted({c["table"] for c in cands} | {x for c in cands for x in c["columns"]})
    if not codes:
        return []
    r = httpx.post(os.environ["GATEWAY_URL"].rstrip("/") + "/v1/answers/dehash", timeout=60,
                   json={"question_id": "qn_00000000", "text": " ".join(codes), "numbers": []})
    r.raise_for_status()
    names = r.json()["text"].split(" ")
    if len(names) != len(codes):
        raise RuntimeError("dehash did not return one name per code")
    name = dict(zip(codes, names))
    return [(name[c["table"]], name[x], name[y]) for c in cands for x, y in zip(c["columns"], c["columns"][1:])]


def _orient(meta: dict, pairs, log) -> list[tuple[str, str, str]]:
    """Pairs to condition, as (table, first, second). A pair whose second column is the primary
    key is flipped. A pair is skipped when its second column is already conditioned, or when
    conditioning it would make a cycle."""
    parent: dict[tuple, tuple] = {}
    out = []
    for t, a, b in pairs:
        if (t, b) in meta["pk"]:
            a, b = b, a
        above, x = {(t, a)}, (t, a)
        while x in parent:
            x = parent[x]
            above.add(x)
        if (t, b) in parent or (t, b) in above or (t, b) in meta["pk"]:
            log(f"twin: pair {t} ({a}, {b}) skipped")
            continue
        parent[(t, b)] = (t, a)
        out.append((t, a, b))
    return out


def _first_keys(meta: dict, maps: dict, t: str, a: str) -> list[list]:
    """[[real, twin], ...] naming the first column's buckets: its frequency-rank map; for a
    primary key, the map of the largest child foreign key that references it (twin parent ID k
    stands for the parent of rank k in that foreign key)."""
    # ponytail: a first column is bucketed by its most-common values only, the rest is one
    # bucket. Enough for the keys the miner flags here (region_id, product_id, store_id); a
    # numeric or date first column would also want its histogram buckets.
    if (t, a) in meta["pk"]:
        children = [k for k, p in meta["fk"].items() if p == t]
        if not children:
            return []
        child, col = max(children, key=lambda k: meta["rows"][k[0]])
        return maps.get(f"{child}.{col}", [])
    return maps.get(f"{t}.{a}", [])


def _joint(conn, t: str, a: str, a_typ: str, keys: list[list], b: str, b_typ: str, mcv: list, hist: list) -> dict:
    """The bucketed table, computed in pg-prod: {(first column's real value or None for the
    rest, second column's bucket): rows}. Second-column buckets match its sampler's intervals:
    pass `hist` only if the sampler draws inside histogram buckets. NULLs in the second column
    are left out: its sampler draws NULLs at its null fraction."""
    if hist:
        rest = sql.SQL("'h:' || LEAST(GREATEST(width_bucket({b}, CAST({h} AS {bt}[])), 1), {n})").format(
            b=sql.Identifier(b), h=sql.Literal(hist), bt=sql.SQL(b_typ), n=sql.Literal(len(hist) - 1))
    else:
        rest = sql.SQL("'r'")
    q = sql.SQL("""SELECT CASE WHEN {a} = ANY(CAST({ak} AS {at}[])) THEN {a}::text END,
                          CASE WHEN {b} = ANY(CAST({bm} AS {bt}[])) THEN 'm:' || {b}::text ELSE {rest} END,
                          count(*)
                   FROM {t} WHERE {b} IS NOT NULL GROUP BY 1, 2""").format(
        a=sql.Identifier(a), ak=sql.Literal([str(r) for r, _ in keys]), at=sql.SQL(a_typ),
        b=sql.Identifier(b), bm=sql.Literal(mcv), bt=sql.SQL(b_typ), rest=rest, t=sql.Identifier(t))
    return {(ra, rb): n for ra, rb, n in conn.execute(q)}


def _conditional_u(rng, keys: list[list], joint: dict, intervals: dict):
    """u_for(first column's twin values) -> u for the second column's draw: per row, a bucket
    of the second column drawn from the bucketed table given the first column's bucket, and u
    uniform inside that bucket's interval. A first-column bucket prod never showed keeps the
    second column's own distribution."""
    code_of = {twin: i for i, (_, twin) in enumerate(keys)}
    real_code = {str(real): i for i, (real, _) in enumerate(keys)}
    rows: dict[int, list] = {}
    for (ra, rb), n in joint.items():
        rb = rb if rb in intervals else "r"       # e.g. a most-common parent the twin has no ID for
        if rb in intervals:
            rows.setdefault(real_code.get(ra, -1), []).append((rb, n))
    table = {}
    for code, bn in rows.items():
        p = np.array([n for _, n in bn], dtype=float)
        lo = np.array([intervals[rb][0] for rb, _ in bn])
        hi = np.array([intervals[rb][1] for rb, _ in bn])
        table[code] = (np.cumsum(p) / p.sum(), lo, hi)

    def u_for(a_vals) -> np.ndarray:
        codes = pd.Series(a_vals).map(code_of).fillna(-1).to_numpy(dtype=np.int64)
        u = rng.random(len(codes))
        for code, (cum, lo, hi) in table.items():
            sel = np.flatnonzero(codes == code)
            pick = np.minimum(np.searchsorted(cum, rng.random(len(sel)), side="right"), len(cum) - 1)
            u[sel] = lo[pick] + rng.random(len(sel)) * (hi[pick] - lo[pick])
        return u
    return u_for


def build(prod_dsn: str, twin_dsn: str, pairs: list[tuple[str, str, str]] | None = None, log=print) -> dict:
    """Fill the twin table by table, parents first, in chunks of workload.copy_batch_rows so
    a 50,000,000-row hero table never sits in memory at once. pairs: (table, first, second)
    to keep correlated; None asks the miner (flagged_pairs)."""
    rng = np.random.default_rng(int(cfg("dataset.random_seed")) + 1)
    batch = int(cfg("workload.copy_batch_rows"))
    pairs = flagged_pairs() if pairs is None else pairs
    with psycopg.connect(prod_dsn) as conn:
        meta = _read_stats(conn)
    sizes = _target_rows(meta)
    # Parents before children.
    order, pending = [], set(meta["tables"])
    while pending:
        ready = sorted(t for t in pending if all(p in order or p == t for (c, _), p in meta["fk"].items() if c == t))
        order += ready
        pending -= set(ready)
    # Every sampler first, so a flagged pair can read another table's frequency-rank map.
    draws, maps, types = {}, {}, {}
    for t in order:
        for col, typ, stat in meta["tables"][t]:
            role = "pk" if (t, col) in meta["pk"] else ("fk" if (t, col) in meta["fk"] else None)
            parent_n = sizes[meta["fk"][(t, col)]] if role == "fk" else 0
            draws[(t, col)], m = _column_sampler(rng, typ, stat, role, parent_n, col)
            types[(t, col)] = (typ, stat)
            if m:
                maps[f"{t}.{col}"] = m
    cond = {}
    with psycopg.connect(prod_dsn, autocommit=True) as conn:
        for t, a, b in _orient(meta, pairs, log):
            keys = _first_keys(meta, maps, t, a)
            intervals = draws[(t, b)].intervals
            b_typ, b_stat = types[(t, b)]
            _, _, _, mcv, _, hist = b_stat or (0, 0.0, 8, None, None, None)
            joint = _joint(conn, t, a, types[(t, a)][0], keys, b, b_typ, list(mcv or []),
                           list(hist or []) if "h:1" in intervals else [])
            cond[(t, b)] = (a, _conditional_u(rng, keys, joint, intervals))
            log(f"twin: {t}.{b} sampled given {t}.{a} ({len(keys)} buckets of {a} plus the rest, {len(joint)} cells)")
    with psycopg.connect(twin_dsn, autocommit=True) as conn:
        conn.execute("TRUNCATE " + ", ".join(order) + " CASCADE")
        # Foreign keys stay declared (pg_dump copied them), but their per-row trigger checks are
        # skipped while loading: every generated foreign key is drawn from 1..parent rows, so it
        # is valid by construction. Needs a superuser, which the tools container connects as.
        conn.execute("SET session_replication_role = replica")
        for t in order:
            cols = [col for col, _, _ in meta["tables"][t]]
            for start in range(0, sizes[t], batch):
                size = min(batch, sizes[t] - start)
                vals = {c: draws[(t, c)](start, size) for c in cols if (t, c) not in cond}
                while len(vals) < len(cols):          # conditioned columns once their first column exists
                    for c in cols:
                        if c not in vals and cond[(t, c)][0] in vals:
                            a, u_for = cond[(t, c)]
                            vals[c] = draws[(t, c)](start, size, u=u_for(vals[a]))
                frame = pd.DataFrame({c: vals[c] for c in cols})
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
    return {"rows": {t: sizes[t] for t in order}, "mapped_columns": len(maps),
            "correlated_pairs": [f"{t}.{b} given {t}.{a}" for (t, b), (a, _) in cond.items()]}


if __name__ == "__main__":
    print(build(os.environ["PROD_DSN"], os.environ["TWIN_DSN"]))
