"""What may never appear on a public page: the demo database's real identifiers and the planted
canary values. Shared by the site tests and scripts/record_ask.py."""
from __future__ import annotations

import re

from db import canaries

# QuickMart's real identifiers: none may appear on the public site.
REAL = ["regions", "stores", "customers", "products", "sales", "returns", "region_id", "store_id", "customer_id",
        "product_id", "order_id", "return_id", "transaction_date", "amount", "full_name", "unit_price",
        "payment_method", "signup_date", "opened_on", "quickmart", "quickmart_app"]


def leaks(text: str) -> list[str]:
    """Every forbidden name (whole word, any case) and canary kind found in text."""
    low = text.lower()
    found = [r for r in REAL if re.search(rf"\b{r}\b", low)]
    found += [f"canary:{c.kind}" for c in canaries.ALL if c.value.lower() in low]
    return found
