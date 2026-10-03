"""Adversarial leak test, AI side (doc, Component 7, Proof 3 step 3; Detailed component specs,
Privacy tests). A fresh LLM session with no tools gets the hashed payloads of one run and is
asked to name the real table or column behind each code.

The payloads come from the gateway (GET /v1/ledger/payloads), so this sends only bytes that
already crossed the boundary. The request goes through llm.generate, so it is canary-scanned
and ledgered like every other LLM payload. Scoring needs the real names, so it happens on the
private side (privacy_tests/adversarial.py); nothing here knows a real name.
"""
from __future__ import annotations

import json
import re

from common.config import cfg

CODE = re.compile(r"\b[tc]_[0-9a-f]{8}\b")

SYSTEM = """You are a privacy auditor running an authorised leak test on our own database tuning
system. Before anything leaves the database host, the system replaces every table name with a
code t_ plus 8 hex characters and every column name with a code c_ plus 8 hex characters.
Below are the payloads one tuning run sent out. For each listed code, guess the most likely
real name, the way a database designer would write it (snake_case). Use every clue: query
shapes, aggregates, filters, joins, column roles, row counts, sizes and distinct counts.
Always guess; never skip a code. Reply with one JSON object that maps each code to your guess,
and nothing else."""


def select(payloads: list[dict], max_chars: int) -> list[dict]:
    """What fits the character budget (the free tier's tokens per minute): LLM request bodies
    first (what the provider itself saw), then AI-side payloads, each in time order; a payload
    that would overflow the budget is skipped.
    ponytail: a Q1 run's search sends about 200 HypoPG costings, so the budget mostly drops
    those; a smarter pick would compress them instead."""
    out, used = [], 0
    for p in sorted(payloads, key=lambda p: p["destination"] != "llm"):
        if used + len(p["body"]) <= max_chars:
            out.append(p)
            used += len(p["body"])
    return out


def user_turn(bodies: list[str], codes: list[str]) -> str:
    return ("Codes to name: " + ", ".join(codes) + "\n\nPayloads, one JSON document per line:\n" + "\n".join(bodies))


def parse_guesses(text: str, codes: list[str]) -> dict[str, str]:
    """The model's guess per code, as written. Codes it skipped or garbled are left out."""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        raw = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    return {c: raw[c] for c in codes if isinstance(raw.get(c), str)}


def run(payloads: list[dict], llm) -> dict:
    # An earlier adversary request in the window is a re-send of kept payloads: leave it out.
    payloads = [p for p in payloads if SYSTEM.split("\n", 1)[0] not in p["body"]]
    sent = select(payloads, int(cfg("privacy.adversarial_max_chars")))
    bodies = [p["body"] for p in sent]
    codes = sorted({c for b in bodies for c in CODE.findall(b)})
    material = {"payloads_in_window": len(payloads), "payloads_sent": len(sent),
                "chars_in_window": sum(len(p["body"]) for p in payloads), "chars_sent": sum(map(len, bodies)),
                "llm_payloads_sent": sum(p["destination"] == "llm" for p in sent)}
    if not codes:                     # nothing to name: no LLM call
        return {"guesses": {}, "codes": [], "model": llm.model, "llm_payload_id": None, "material": material}
    resp = llm.generate(SYSTEM, [{"role": "user", "parts": [{"text": user_turn(bodies, codes)}]}], [])
    parts = resp["candidates"][0]["content"].get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return {"guesses": parse_guesses(text, codes), "codes": codes, "model": llm.model,
            "llm_payload_id": llm.last_entry["payload_id"], "material": material}
