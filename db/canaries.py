"""Canary tokens (architecture doc, "Canary placement"): 20 fake values planted where a leak
would carry them. If any of them, or any 6-character fragment of one, appears in a payload
bound for the AI side, privacy failed.

This file lives on the private side. The gateway's scanner imports it; the ai container
never mounts db/.

Values avoid English words: the scanner also matches any 6-character fragment, case-
insensitively, so a canary such as CANARY_COMMENT_... would block ordinary text containing
"recommended" (that happened on the first live LLM run, 2026-10-03). db/tests/test_canaries.py
checks every fragment against the agent's prompts and the architecture doc's English.

Each canary has a stable ID (cn_ plus the first 8 hex of SHA-256 of its value), so the
ledger can record a hit without storing the value itself.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Canary:
    kind: str     # where it is planted
    value: str    # the planted text, exactly as stored or sent

    @property
    def canary_id(self) -> str:
        return "cn_" + hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:8]


# 5 emails, 3 names, 2 phones (customers rows)
EMAILS = [Canary("customer_email", f"CANARY_{n}@corp.com") for n in (7731, 7732, 7733, 7734, 7735)]
NAMES = [Canary("customer_name", v) for v in ("Quillon Vexmarrow", "Ottilie Brannagh-Zest", "Corvin Hzalweth")]
PHONES = [Canary("customer_phone", v) for v in ("+91-98731-77310", "+91-98731-77320")]
# 3 sale amounts and 2 product names (sales and products rows)
AMOUNTS = [Canary("sale_amount", v) for v in ("7731.77", "8842.88", "9953.99")]
PRODUCTS = [Canary("product_name", v) for v in ("Zephyrine Kettle KX-7731", "Marrowind Lamp ML-7732")]
# 2 query comments and 2 filter values (workload queries, see db/workload.py)
COMMENTS = [Canary("query_comment", v) for v in ("CANARY_QXZ7731_VK", "CANARY_QXZ7732_VK")]
FILTERS = [EMAILS[0], NAMES[0]]   # the two filter queries reuse planted row values
# 1 canary inside the DBA's chat question (used by the dashboard and e2e)
QUESTION = Canary("dba_question", "CANARY_ASK_7731")

ROW_CANARIES = EMAILS + NAMES + PHONES + AMOUNTS + PRODUCTS
ALL: list[Canary] = ROW_CANARIES + COMMENTS + [QUESTION]
# FILTERS reuse row values, so ALL holds 18 distinct values; the doc's "about 20" counts
# placements: 5 + 3 + 2 + 3 + 2 + 2 + 2 + 1 = 20.
PLACEMENTS = len(ROW_CANARIES) + len(COMMENTS) + len(FILTERS) + 1
