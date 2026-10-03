"""Validate objects against the frozen contracts in contracts/schemas/.

Usage from any component:

    from contracts.validate import validate
    validate("HashedPlan", plan_dict)   # raises jsonschema.ValidationError

Checked against jsonschema 4.26.0 and referencing 0.37.0 (the pinned versions).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, dict], Registry]:
    schemas: dict[str, dict] = {}
    resources = []
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[path.name.removesuffix(".schema.json")] = schema
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return schemas, Registry().with_resources(resources)


def contract_names() -> list[str]:
    """Every contract name, excluding the shared definitions file."""
    return sorted(n for n in _load()[0] if n != "common")


def schema(name: str) -> dict:
    return _load()[0][name]


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    schemas, registry = _load()
    return Draft202012Validator(schemas[name], registry=registry)


def validate(name: str, instance: object) -> None:
    """Raise jsonschema.ValidationError if instance breaks the named contract."""
    validator(name).validate(instance)


def errors(name: str, instance: object) -> list[str]:
    """All validation error messages, empty when the instance is valid."""
    return [e.message for e in validator(name).iter_errors(instance)]
