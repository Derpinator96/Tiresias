"""Ask the VeriEQL service (verify/verieql_server.py, private network) whether two real queries
are equivalent. Private side: real SQL and real names, never sent to ai.

Schema and constraints come from the gateway's catalog: primary keys and NOT NULL columns.
Types map to VeriEQL's INT, VARCHAR, DATE and BOOLEAN. ASSUMPTION: numeric columns (amounts,
prices) are modelled as INT, which is exact for the comparisons our rules rewrite but not
for decimal arithmetic. Bounded: "pass" means equivalent for every database up to
verify.verieql_rows_per_table rows per table, not for all sizes.
"""
from __future__ import annotations

import os

import httpx

from common.config import cfg

TYPES = {"integer": "INT", "bigint": "INT", "smallint": "INT", "numeric": "INT", "real": "INT",
         "double precision": "INT", "date": "DATE", "text": "VARCHAR", "character varying": "VARCHAR",
         "boolean": "BOOLEAN"}


def schema_and_constraints(catalog) -> tuple[dict, list]:
    schema = {t.upper(): {c.upper(): TYPES.get(typ, "VARCHAR") for c, typ in cols.items()}
              for t, cols in catalog.columns.items()}
    cons = [{"not_null": {"value": f"{t.upper()}__{c.upper()}"}}
            for t, cols in catalog.columns.items() for c in cols if (t, c) not in catalog.nullable]
    for t in catalog.columns:
        pk = [c for (tt, c) in sorted(catalog.pk) if tt == t]
        if pk:
            cons.append({"primary": [{"value": f"{t.upper()}__{c.upper()}"} for c in pk]})
    return schema, cons


def check(sql1: str, sql2: str, catalog) -> dict:
    """{"result": "pass" | "fail" | "unsupported" | "not_run", "detail": str}."""
    schema, cons = schema_and_constraints(catalog)
    timeout = int(cfg("verify.verieql_timeout_s"))
    try:
        r = httpx.post(os.environ["VERIEQL_URL"].rstrip("/") + "/check", timeout=timeout + 30,
                       json={"sql1": sql1, "sql2": sql2, "schema": schema, "constraints": cons,
                             "bound": int(cfg("verify.verieql_rows_per_table")), "timeout_s": timeout})
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, KeyError) as e:
        return {"result": "not_run", "detail": f"verifier unreachable: {type(e).__name__}"}
