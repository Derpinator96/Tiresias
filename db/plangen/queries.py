"""Query instances for DSB and TPC-H, generated with each kit's own tool (dsqgen, qgen) so
parameters follow the benchmark's own distributions.

Facts below were read from the kits' sources at the pinned commits (infra/bench/Dockerfile),
not from memory:
- DSB: Postgres templates live in query_templates_pg/{spj_queries,agg_queries,
  multi_block_queries}/, each folder with its own postgres.tpl dialect file. dsqgen takes
  -output_dir -streams -directory -template -dialect -scale -rngseed and writes
  query_0.sql .. query_<streams-1>.sql. It must run from code/tools, where tpcds.idx is.
- TPC-H: qgen reads $DSS_QUERY/<n>.sql and $DSS_CONFIG/dists.dss; -s scale, -r seed.
  Templates write `interval '<n>' day (3)`, which Postgres rejects, and template 1 ends in
  `limit -1`; both are fixed here. Template 15 creates and drops a view, so it is skipped.
UNVERIFIED until the bench image runs: dsqgen's exact output wrapping (comments, multiple
statements per file). split_statements() handles both.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

DSB_FAMILIES = ("spj_queries", "agg_queries", "multi_block_queries")
TPCH_TEMPLATES = [n for n in range(1, 23) if n != 15]


def split_statements(text: str) -> list[str]:
    """Statements in a generated query file, with -- comments removed."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def fix_tpch(sql: str) -> str:
    sql = re.sub(r"day\s*\(\s*3\s*\)", "day", sql)
    return re.sub(r"limit\s+-1", "", sql, flags=re.I).strip()


def dsb_instances(n_sets: int, seed: int, scale: int) -> list[tuple[str, bool, list[str]]]:
    home = Path(os.environ["DSB_HOME"])
    tools = home / "tools"
    out = []
    for family in DSB_FAMILIES:
        folder = home / "query_templates_pg" / family
        for tpl in sorted(folder.glob("query*.tpl")):
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run([str(tools / "dsqgen"), "-output_dir", tmp, "-streams", str(n_sets),
                                "-directory", str(folder), "-template", tpl.name, "-dialect", "postgres",
                                "-scale", str(scale), "-rngseed", str(seed)],
                               cwd=tools, check=True, capture_output=True, text=True)
                per_set = [split_statements((Path(tmp) / f"query_{i}.sql").read_text(encoding="latin-1"))
                           for i in range(n_sets)]
            base = f"dsb/{family.split('_')[0]}/{tpl.stem}"
            for j in range(max(len(s) for s in per_set)):
                sqls = [s[j] for s in per_set if len(s) > j]
                if len(sqls) == n_sets:
                    out.append((base if j == 0 else f"{base}#{j}", False, sqls))
    return out


def tpch_instances(n_sets: int, seed: int, scale: int) -> list[tuple[str, bool, list[str]]]:
    dbgen = Path(os.environ["TPCH_HOME"]) / "dbgen"
    env = {**os.environ, "DSS_CONFIG": str(dbgen), "DSS_QUERY": str(dbgen / "queries")}
    out = []
    for n in TPCH_TEMPLATES:
        sqls = []
        for i in range(n_sets):
            res = subprocess.run([str(dbgen / "qgen"), "-s", str(scale), "-r", str(seed + i), str(n)],
                                 cwd=dbgen, env=env, check=True, capture_output=True, text=True)
            stmts = split_statements(res.stdout)
            sqls.append(fix_tpch(stmts[0]))
        out.append((f"tpch/q{n:02d}", False, sqls))
    return out
