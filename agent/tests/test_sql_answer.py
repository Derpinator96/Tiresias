"""Data questions (agent/sql_answer.py, /ai/sql) with a fake provider: no key, no network."""
import pytest
from fastapi import HTTPException

from agent import api, llm, sql_answer

SCHEMA = [{"table": "products", "columns": [{"name": "product_id", "type": "bigint"}, {"name": "name", "type": "text"}]},
          {"table": "sales", "columns": [{"name": "product_id", "type": "bigint"}, {"name": "quantity", "type": "integer"}]}]


def test_split_fenced_reply():
    text = "Sums units per product.\n```sql\nSELECT name FROM products LIMIT 5;\n```\nThanks"
    assert sql_answer.split_sql_reply(text) == ("Sums units per product.", "SELECT name FROM products LIMIT 5")


def test_split_unfenced_reply_starts_at_select_or_with():
    assert sql_answer.split_sql_reply("Top product. WITH t AS (SELECT 1) SELECT * FROM t;") == (
        "Top product.", "WITH t AS (SELECT 1) SELECT * FROM t")


def test_split_reply_without_sql():
    assert sql_answer.split_sql_reply("I cannot answer that.") == ("I cannot answer that.", "")


def test_prompt_holds_names_and_types_but_no_rows():
    turn = sql_answer.user_turn("which product sold most?", SCHEMA)
    assert "products(product_id bigint, name text)" in turn and "which product sold most?" in turn


class Fake:
    model = "fake-model"

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.seen = reply, error, []

    def generate(self, system, contents, declarations, on_event=None):
        self.seen.append((system, contents, declarations))
        if self.error:
            raise self.error
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": self.reply}]}}]}


def test_ai_sql_fails_over_and_returns_explanation_and_sql(monkeypatch):
    first, second = Fake(error=llm.MissingKey("no key")), Fake("Counts units.\n```sql\nSELECT 1\n```")
    by_name = {"nim": first, "gemini": second}
    monkeypatch.setattr(llm, "chain", lambda name=None: ["nim", "gemini"])
    monkeypatch.setattr(llm, "provider", lambda transport=None, name=None, **k: by_name[name])
    out = api.ai_sql({"question": "which product sold most?", "schema": SCHEMA})
    assert out["sql"] == "SELECT 1" and out["explanation"] == "Counts units."
    assert out["llm"] == {"provider": "gemini", "model": "fake-model"} and out["failovers"][0]["provider"] == "nim"
    assert second.seen[0][2] == []                       # no tools on this path


def test_ai_sql_needs_question_and_schema():
    with pytest.raises(HTTPException) as e:
        api.ai_sql({"question": "x", "schema": []})
    assert e.value.status_code == 400
