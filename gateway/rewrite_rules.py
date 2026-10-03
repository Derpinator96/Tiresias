"""Rewrite rule library (doc, Component 4 item 5: rewrites come from a fixed rule library, and
only rules that match a query's shape are offered). Private side: rules match on hashed SQL
(shape only, every literal is `?`) so the AI can choose one, and apply on real SQL, where the
values decide whether the rewrite is valid.

SIMPLIFIED, label LABEL: three built-in rules written for QuickMart's query shapes; RAG over
R-Bot's rule base is MISSING.

Every rewrite is still checked before anyone trusts it (VeriEQL plus a twin checksum).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Callable

import sqlglot
from sqlglot import exp

LABEL = "rewrite rules: 3 built-in rules (R-Bot rule retrieval pending)"
VALUE = (exp.Literal, exp.Placeholder)


class NotApplicable(Exception):
    """The query has the rule's shape, but its values make the rewrite wrong (for example a
    date_trunc compared to a date that is not on a month boundary)."""


def _value(node: exp.Expression) -> exp.Expression | None:
    """The literal or placeholder on one side of a comparison, unwrapping a ::date cast."""
    if isinstance(node, exp.Cast):
        node = node.this
    return node if isinstance(node, VALUE) else None


def _iso(node: exp.Expression) -> date:
    if not (isinstance(node, exp.Literal) and node.is_string):
        raise NotApplicable("the compared value is not a date literal")
    try:
        return date.fromisoformat(node.this[:10])
    except ValueError:
        raise NotApplicable("the compared value is not a date") from None


def _range(col: exp.Expression, lo: exp.Expression, hi: exp.Expression) -> exp.Expression:
    return exp.paren(exp.and_(exp.GTE(this=col.copy(), expression=lo), exp.LT(this=col.copy(), expression=hi)))


def _date_lit(d: date) -> exp.Expression:
    return exp.Literal.string(d.isoformat())


# ---- rule 1: date_trunc('unit', col) = d  ->  col >= d AND col < d + 1 unit -------------------
UNITS = {"DAY", "MONTH", "YEAR"}


def _unit(node: exp.TimestampTrunc) -> str | None:
    u = node.args.get("unit")
    if isinstance(u, exp.Var):
        return u.name.upper()
    if isinstance(u, exp.Literal) and u.is_string:
        return u.this.upper()
    return None   # a placeholder in hashed SQL


def _next(d: date, unit: str) -> date:
    if unit == "DAY":
        return date.fromordinal(d.toordinal() + 1)
    if unit == "MONTH":
        return date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return date(d.year + 1, 1, 1)


def _on_boundary(d: date, unit: str) -> bool:
    return unit == "DAY" or (d.day == 1 and (unit == "MONTH" or d.month == 1))


def _trunc_sides(node: exp.Expression):
    if isinstance(node, exp.EQ):
        for f, v in ((node.this, node.expression), (node.expression, node.this)):
            if isinstance(f, exp.TimestampTrunc) and isinstance(f.this, exp.Column) and _value(v) is not None:
                return f, _value(v)
    return None


def _date_trunc(node: exp.Expression, real: bool) -> exp.Expression:
    sides = _trunc_sides(node)
    if not sides:
        return node
    f, v = sides
    if not real:
        return _range(f.this, exp.Placeholder(jdbc=True), exp.Placeholder(jdbc=True))
    unit = _unit(f)
    if unit not in UNITS:
        raise NotApplicable(f"date_trunc unit {unit} is not supported")
    d = _iso(v)
    if not _on_boundary(d, unit):
        raise NotApplicable("the compared date is not on a unit boundary, so the range would differ")
    return _range(f.this, _date_lit(d), _date_lit(_next(d, unit)))


# ---- rule 2: EXTRACT(YEAR FROM col) = y  ->  col >= 'y-01-01' AND col < 'y+1-01-01' -------------
def _year_sides(node: exp.Expression):
    if isinstance(node, exp.EQ):
        for f, v in ((node.this, node.expression), (node.expression, node.this)):
            if (isinstance(f, exp.Extract) and isinstance(f.this, exp.Var) and f.this.name.upper() == "YEAR"
                    and isinstance(f.expression, exp.Column) and _value(v) is not None):
                return f, _value(v)
    return None


def _extract_year(node: exp.Expression, real: bool) -> exp.Expression:
    sides = _year_sides(node)
    if not sides:
        return node
    f, v = sides
    if not real:
        return _range(f.expression, exp.Placeholder(jdbc=True), exp.Placeholder(jdbc=True))
    if not (isinstance(v, exp.Literal) and not v.is_string and v.this.isdigit()):
        raise NotApplicable("the compared year is not an integer literal")
    y = int(v.this)
    return _range(f.expression, _date_lit(date(y, 1, 1)), _date_lit(date(y + 1, 1, 1)))


# ---- rule 3: c = a OR c = b [OR ...]  ->  c IN (a, b, ...) -----------------------------------
def _disjuncts(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.Paren):
        return _disjuncts(node.this)
    if isinstance(node, exp.Or):
        return _disjuncts(node.this) + _disjuncts(node.expression)
    return [node]


def _or_in(node: exp.Expression, real: bool) -> exp.Expression:
    if not isinstance(node, exp.Or) or isinstance(node.parent, exp.Or):
        return node   # handle each OR chain once, at its top
    parts = _disjuncts(node)
    cols, vals = set(), []
    for p in parts:
        if not (isinstance(p, exp.EQ) and isinstance(p.this, exp.Column) and _value(p.expression) is not None):
            return node
        cols.add(p.this.sql())
        vals.append(_value(p.expression).copy())
    if len(cols) != 1 or len(parts) < 2:
        return node
    return exp.paren(exp.In(this=parts[0].this.copy(), expressions=vals))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    fn: Callable[[exp.Expression, bool], exp.Expression]


RULES = {r.rule_id: r for r in (
    Rule("date_trunc_eq_to_range", "date_trunc(unit, column) = date becomes a range on the bare column, so an index on it can be used", _date_trunc),
    Rule("extract_year_eq_to_range", "EXTRACT(YEAR FROM column) = year becomes a range on the bare column", _extract_year),
    Rule("or_same_column_to_in", "column = a OR column = b becomes column IN (a, b)", _or_in),
)}


def _apply(sql: str, rule_id: str, real: bool) -> str | None:
    tree = sqlglot.parse_one(sql, read="postgres")
    fn = RULES[rule_id].fn
    changed = []

    def step(node):
        new = fn(node, real)
        if new is not node:
            changed.append(1)
        return new
    out = tree.transform(step)
    return out.sql(dialect="postgres") if changed else None


def matching(hashed_sql: str) -> list[str]:
    """Rule IDs whose shape matches this (hashed or real) query."""
    return [rid for rid in RULES if _apply(hashed_sql, rid, real=False) is not None]


def rewrite_shape(hashed_sql: str, rule_id: str) -> str:
    """The rewritten query with every value as `?`, safe to show on the AI side."""
    out = _apply(hashed_sql, rule_id, real=False)
    if out is None:
        raise NotApplicable("the rule does not match this query")
    return out


def rewrite(real_sql: str, rule_id: str) -> str:
    """The rewritten real query. Raises NotApplicable if the shape or values do not allow it."""
    out = _apply(real_sql, rule_id, real=True)
    if out is None:
        raise NotApplicable("the rule does not match this query")
    return out
