"""Verification on the AI side: asks the gateway to compare result checksums on the twin.

Walking skeleton: checksum only. Status for an index config is "Verified" in the doc's sense
only when VeriEQL also passes; with VeriEQL MISSING, a matching checksum is reported as
"TestedOnly", which is the doc's label for "checksum passes, VeriEQL cannot run".

TODO(VeriEQL): add the VeriEQL check (bound verify.verieql_rows_per_table, timeout
verify.verieql_timeout_s) for rewrites, and report "Verified" when both pass.
"""
from __future__ import annotations

from agent import gateway_client as gw


def index_config(template_id: str, config: dict) -> dict:
    r = gw.post("/v1/twin/checksum", {"template_id": template_id, "config": config})
    return {**r, "status": "TestedOnly" if r["match"] else "Rejected",
            "checks": {"verieql": "not_run", "checksum": "match" if r["match"] else "mismatch"}}
