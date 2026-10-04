"""Data questions from the local web app: the LLM writes one SELECT from the schema.

Privacy (human decision 2026-10-04): this path sends the DBA's question and the real table and
column names and types. It never sends rows or values; the gateway runs the SQL on the private
side (/v1/private/query) and the rows go to the DBA's browser only. The request body is
canary-scanned and ledgered like every LLM body (llm._send)."""
from __future__ import annotations

import re

from agent import agent as agent_mod
from agent import llm

SYSTEM = """You write PostgreSQL for a DBA. You get a question and the database schema (table
and column names with types). You never see any rows. Reply in exactly this form:
one sentence saying what the query computes, then the query in a ```sql block.
Rules: one SELECT statement only (a WITH clause is fine), no writes, no semicolon chains, at most
LIMIT {max_rows}. Join on matching *_id columns. Give columns readable aliases."""

FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def user_turn(question: str, schema: list[dict]) -> str:
    lines = [f"{t['table']}({', '.join(c['name'] + ' ' + c['type'] for c in t['columns'])})" for t in schema]
    return "Schema:\n" + "\n".join(lines) + f"\n\nQuestion: {question}"


def split_sql_reply(text: str) -> tuple[str, str]:
    """(explanation, sql) from the model's reply. SQL is the first fenced block, else the text
    from the first SELECT or WITH; empty when there is none."""
    m = FENCE.search(text)
    if m:
        return (text[:m.start()].strip(), m.group(1).strip().rstrip(";").strip())
    m = re.search(r"\b(WITH|SELECT)\b", text, re.I)
    if not m:
        return (text.strip(), "")
    return (text[:m.start()].strip(), text[m.start():].strip().rstrip(";").strip())


def ask_sql(question: str, schema: list[dict], max_rows: int, name: str | None = None,
            transport=None) -> dict:
    """One completion with no tools, failing over along llm.chain() like /ai/ask."""
    names, failovers = llm.chain(name), []
    contents = [{"role": "user", "parts": [{"text": user_turn(question, schema)}]}]
    for i, n in enumerate(names):
        try:
            p = llm.provider(transport, name=n)
            out = p.generate(SYSTEM.format(max_rows=max_rows), contents, [])
            break
        except llm.FAILOVER_ERRORS as e:
            if i == len(names) - 1:
                raise
            failovers.append({"provider": n, "error": f"{type(e).__name__}: {str(e)[:200]}"})
    explanation, sql = split_sql_reply(agent_mod._text(out["candidates"][0]["content"]))
    return {"explanation": explanation, "sql": sql, "llm": {"provider": n, "model": p.model}, "failovers": failovers}
