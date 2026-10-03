"""Contract tests: every schema is well formed, every valid example passes, every invalid one fails.

The invalid examples are the privacy rules in executable form: real names, literals, comments,
short codes and pg_stats value lists must all be rejected by the schemas themselves.
"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from contracts.validate import contract_names, errors, schema

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# Every contract in the architecture doc's "Interface contracts" table, plus the approved
# OutboundPayload (decision I in PLAN.md).
EXPECTED = {
    "HashedQuery", "HashedPlan", "ColumnMeta", "TableMeta", "Candidate", "Config",
    "Prediction", "SimResult", "Rewrite", "LedgerEntry", "Answer", "OutboundPayload",
}

# Real QuickMart names that must never appear in a valid example.
REAL_NAMES = [
    "regions", "stores", "customers", "products", "sales", "returns",
    "region_id", "store_id", "customer_id", "product_id", "order_id", "return_id",
    "transaction_date", "amount", "email", "full_name", "phone", "city", "payment_method",
]


def _load(kind):
    out = []
    for path in sorted((EXAMPLES / kind).glob("*.json")):
        for i, item in enumerate(json.loads(path.read_text(encoding="utf-8"))):
            out.append(pytest.param(path.stem, item, id=f"{path.stem}-{i}"))
    return out


def test_every_contract_has_a_schema():
    assert set(contract_names()) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED | {"common"}))
def test_schema_is_valid_draft_2020_12(name):
    Draft202012Validator.check_schema(schema(name))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_contract_has_valid_and_invalid_examples(name):
    assert (EXAMPLES / "valid" / f"{name}.json").exists()
    assert (EXAMPLES / "invalid" / f"{name}.json").exists()


@pytest.mark.parametrize("name,instance", _load("valid"))
def test_valid_example_passes(name, instance):
    assert errors(name, instance) == []


@pytest.mark.parametrize("name,case", _load("invalid"))
def test_invalid_example_fails(name, case):
    assert errors(name, case["instance"]), f"accepted but should reject: {case['why']}"


@pytest.mark.parametrize("name,instance", _load("valid"))
def test_valid_examples_hold_no_real_names(name, instance):
    text = json.dumps(instance).lower()
    for real in REAL_NAMES:
        assert f'"{real}"' not in text and f" {real} " not in text, real
