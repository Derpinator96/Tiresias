"""Adversarial leak test, private side (doc, Component 7, Proof 3 step 3, and Detailed component
specs, Privacy tests). Run in the tools container after a run that reached the LLM:

    make adversarial                      # window of the last passing e2e run (runs/latest.json)
    python -m privacy_tests.adversarial SINCE UNTIL     # any window, ISO times with a timezone

1. ai's POST /ai/privacy/adversary gives a fresh LLM session (no tools) the hashed payloads the
   gateway kept for that window and returns the model's guess per code. That request goes
   through the gateway's outbound ledger and canary scan like every other LLM payload.
2. The real name behind each code comes from the gateway's private dehash endpoint.
3. Each guess scores exact, synonym or none. The baseline is the expected score of a uniform
   random guess from a list of common names of the same kind (table or column).
4. Writes runs/adversarial.json: counts, rates and a match flag per code. No real name and no
   guess goes into the file, so it can be exported as is.

Plaintext control (doc: "compare with a plaintext control"): real names are never sent to the
external LLM, not even as a control. The plaintext figure is the upper bound by construction
(plaintext payloads carry every real name verbatim, so an adversary reading them names 100%);
an LLM run on plaintext is pending air-gapped mode, where the model is local.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import httpx

from common.config import REPO_ROOT, cfg

LABEL = ("adversarial leak test: a fresh LLM session guesses table and column names from one run's payloads "
         "(values not scored; plaintext LLM control pending air-gapped mode)")
OUT = REPO_ROOT / "runs" / "adversarial.json"
LAST_E2E = REPO_ROOT / "runs" / "latest.json"

# Common names a guesser would try first, written as generic schema vocabulary (not taken from
# QuickMart). They include QuickMart's own names where those are common: that is the chance level.
COMMON = {
    "table": ["users", "customers", "orders", "order_items", "products", "items", "sales", "transactions",
              "payments", "invoices", "accounts", "employees", "departments", "stores", "locations", "regions",
              "countries", "cities", "addresses", "categories", "suppliers", "vendors", "inventory", "shipments",
              "returns", "refunds", "reviews", "sessions", "events", "logs", "carts", "coupons", "subscriptions",
              "plans", "contacts", "companies", "projects", "tasks", "messages", "notifications"],
    "column": ["id", "name", "email", "phone", "address", "city", "country", "region", "status", "type",
               "created_at", "updated_at", "date", "amount", "price", "quantity", "total", "description", "title",
               "category", "user_id", "customer_id", "order_id", "product_id", "store_id", "region_id", "account_id",
               "payment_id", "category_id", "first_name", "last_name", "full_name", "password", "username", "code",
               "sku", "brand", "unit_price", "discount", "tax", "currency", "payment_method", "order_date",
               "transaction_date", "due_date", "start_date", "end_date", "signup_date", "is_active", "notes",
               "rating", "reason", "segment", "zip", "state", "latitude", "longitude", "url", "count", "score"],
}

# Real QuickMart name -> names that mean the same thing. Small on purpose (doc: "a small
# synonym list"); a guess outside it scores none even when it is close.
SYNONYMS = {
    "sales": {"sale", "orders", "order", "transactions", "transaction", "sales_orders", "order_items"},
    "customers": {"customer", "users", "user", "clients", "client", "buyers"},
    "products": {"product", "items", "item", "skus", "catalog"},
    "stores": {"store", "shops", "shop", "outlets", "branches", "locations"},
    "regions": {"region", "areas", "territories", "zones"},
    "returns": {"return", "refunds", "refund", "returned_items", "order_returns"},
    "order_id": {"sale_id", "transaction_id", "sales_id"},
    "customer_id": {"user_id", "client_id", "buyer_id"},
    "product_id": {"item_id", "sku", "sku_id"},
    "store_id": {"shop_id", "location_id", "branch_id", "outlet_id"},
    "region_id": {"area_id", "territory_id", "zone_id"},
    "return_id": {"refund_id"},
    "transaction_date": {"order_date", "sale_date", "sales_date", "purchase_date", "txn_date", "transaction_at"},
    "amount": {"total", "total_amount", "revenue", "sale_amount", "order_total", "net_amount"},
    "quantity": {"qty", "units", "quantity_sold"},
    "payment_method": {"payment_type", "payment_mode", "tender_type"},
    "unit_price": {"price", "list_price"},
    "email": {"email_address"},
    "full_name": {"name", "customer_name"},
    "phone": {"phone_number", "mobile"},
    "city": {"town"},
    "signup_date": {"registration_date", "joined_on", "join_date", "signup_at"},
    "segment": {"customer_segment", "tier"},
    "name": {"product_name", "title"},
    "category": {"product_category"},
    "brand": {"manufacturer"},
    "opened_on": {"open_date", "opened_at", "opening_date"},
    "region_name": {"name"},
    "return_date": {"refund_date", "returned_on", "returned_at"},
    "reason": {"return_reason"},
}


def normalise(guess: str) -> str:
    g = guess.strip().strip("\"'`").lower().rsplit(".", 1)[-1]
    return re.sub(r"[\s-]+", "_", g.strip())


def match(guess: str, real: str) -> str:
    g = normalise(guess)
    return "exact" if g == real else "synonym" if g in SYNONYMS.get(real, ()) else "none"


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    exact = sum(r["match"] == "exact" for r in rows)
    syn = sum(r["match"] == "synonym" for r in rows)
    return {"codes": n, "exact": exact, "synonym": syn,
            "exact_rate": round(exact / n, 4) if n else 0.0, "rate": round((exact + syn) / n, 4) if n else 0.0}


def score(guesses: dict[str, str], truth: dict[str, tuple[str, str]]) -> dict:
    """truth: code -> (kind, real name). A code the model skipped scores none."""
    per = [{"code": c, "kind": k, "match": match(guesses.get(c, ""), real)} for c, (k, real) in sorted(truth.items())]
    return {"all": _agg(per), "table": _agg([r for r in per if r["kind"] == "table"]),
            "column": _agg([r for r in per if r["kind"] == "column"]), "per_code": per}


def baseline(truth: dict[str, tuple[str, str]]) -> dict:
    """Expected score of one uniform random guess per code from COMMON of the code's kind."""
    def p(kind: str, real: str, ok: tuple[str, ...]) -> float:
        return sum(match(n, real) in ok for n in COMMON[kind]) / len(COMMON[kind])
    rows = list(truth.values())
    n = len(rows) or 1
    return {"exact_rate": round(sum(p(k, r, ("exact",)) for k, r in rows) / n, 4),
            "rate": round(sum(p(k, r, ("exact", "synonym")) for k, r in rows) / n, 4),
            "table_names_listed": len(COMMON["table"]), "column_names_listed": len(COMMON["column"])}


def last_e2e_window() -> tuple[str, str]:
    run = json.loads(LAST_E2E.read_text(encoding="utf-8"))
    end = datetime.fromisoformat(run["finished_at"].replace("Z", "+00:00")) + timedelta(seconds=1)
    return (end - timedelta(seconds=run["elapsed_s"] + 2)).isoformat(), end.isoformat()


def main(argv: list[str]) -> int:
    since, until = argv[1:3] if len(argv) >= 3 else last_e2e_window()
    gw, ai = os.environ["GATEWAY_URL"], os.environ["AI_URL"]
    r = httpx.post(ai + "/ai/privacy/adversary", json={"since": since, "until": until}, timeout=900)
    if r.status_code != 200:
        print(f"adversary run failed: HTTP {r.status_code} {r.text[:300]}")
        return 1
    adv = r.json()
    if not adv["codes"]:
        print("no table or column code in that window's payloads: nothing to score")
        return 1
    text = "\n".join(adv["codes"])
    names = httpx.post(gw + "/v1/answers/dehash", json={"question_id": "qn_00000000", "text": text, "numbers": []},
                       timeout=120).raise_for_status().json()["text"].split("\n")
    truth = {c: ("table" if c[0] == "t" else "column", n) for c, n in zip(adv["codes"], names) if n != c}
    sc = score(adv["guesses"], truth)
    result = {
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"since": since, "until": until},
        "llm": {"provider": cfg("llm.provider"), "model": adv["model"], "temperature": cfg("llm.temperature"),
                "llm_payload_id": adv["llm_payload_id"], "guesses_returned": len(adv["guesses"])},
        "material": adv["material"],
        "codes_unresolved": len(adv["codes"]) - len(truth),
        "hashed": {k: sc[k] for k in ("all", "table", "column")},
        "baseline_random_common_names": baseline(truth),
        "plaintext_upper_bound": {"rate": 1.0, "assumption": "by construction: plaintext payloads carry every real name verbatim; not an LLM run"},
        "plaintext_llm_control": "pending air-gapped mode: real names are never sent to the external LLM",
        "per_code": sc["per_code"],
        "label": LABEL,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    a, b = result["hashed"]["all"], result["baseline_random_common_names"]
    print(f"adversary named {a['exact'] + a['synonym']} of {a['codes']} codes ({a['exact']} exact, {a['synonym']} synonym), "
          f"rate {a['rate']}; random common-name baseline {b['rate']}; wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
