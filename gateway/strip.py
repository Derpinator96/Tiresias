"""Hash names and strip literals and comments with the sqlglot parse tree, never regex
(doc, Component 1 and Detailed component specs).

Checked against sqlglot 30.21.0 (the pinned version):
- Postgres `$1` parses as Parameter(Literal(1)); the whole Parameter node is replaced.
- comments are dropped by rendering with comments=False.
- output is rendered in sqlglot's generic dialect, where a Placeholder prints as `?`
  (the postgres dialect prints `%s`, which the contract would reject).

Fail closed: anything that does not parse, names an unknown table, has an ambiguous column,
or leaves any identifier that is not a code raises Unparsed, and nothing is sent.
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from contracts.validate import schema as contract_schema
from gateway.hashing import Hasher

_HASHED_SQL = contract_schema("common")["$defs"]["hashed_sql"]
_HASHED_RE = re.compile(_HASHED_SQL["pattern"])
_FORBIDDEN_RE = re.compile(_HASHED_SQL["not"]["pattern"])
_CODE_RE = re.compile(r"^[tcqi]_[0-9a-f]{8}$")

Schema = dict[str, set[str]]   # real table -> its real column names


class Unparsed(Exception):
    """Raised instead of ever returning text that might hold a raw value or real name."""


def _check_output(text: str, tree: exp.Expression) -> str:
    for ident in tree.find_all(exp.Identifier):
        if not _CODE_RE.match(ident.name):
            raise Unparsed("an identifier survived hashing")
    if not _HASHED_RE.fullmatch(text) or _FORBIDDEN_RE.search(text):
        raise Unparsed("output does not match the hashed_sql contract")
    return text


def _replace_values(tree: exp.Expression) -> exp.Expression:
    def swap(node):
        if isinstance(node, (exp.Parameter, exp.Literal, exp.Placeholder)):
            return exp.Placeholder()
        return node
    return tree.transform(swap, copy=False)


def _role_of(col: exp.Column) -> str | None:
    """Role of a column from its nearest enclosing clause or comparison."""
    node = col.parent
    while node is not None:
        if isinstance(node, (exp.EQ, exp.NEQ)):
            if isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Column):
                return "JOIN"
            # A column wrapped in a function (date_trunc(...) = ?) is not sargable: no role.
            return "EQ" if (node.this is col or node.expression is col) else None
        if isinstance(node, exp.In):
            return "EQ" if node.this is col else None
        if isinstance(node, (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
            return "RANGE" if (node.this is col or getattr(node, "expression", None) is col) else None
        if isinstance(node, exp.Group):
            return "GROUP"
        if isinstance(node, exp.Ordered):
            return "ORDER"
        if isinstance(node, exp.Where) or isinstance(node, exp.Join):
            return None
        if isinstance(node, exp.Select):
            return "SELECT"
        node = node.parent
    return None


def hash_sql(sql: str, hasher: Hasher, schema: Schema) -> tuple[str, list[dict]]:
    """Return (hashed SQL, [{table, col, role}]) for one statement. Raises Unparsed."""
    try:
        tree = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as e:  # sqlglot raises several error types; all mean "do not send"
        raise Unparsed(f"parse failed: {type(e).__name__}") from None
    if tree is None:
        raise Unparsed("empty statement")

    tables = list(tree.find_all(exp.Table))
    if not tables:
        raise Unparsed("no table")
    alias_map: dict[str, str] = {}
    for t in tables:
        if t.name not in schema or t.args.get("db"):
            raise Unparsed("unknown table")
        alias_map[t.alias_or_name] = t.name
        alias_map[t.name] = t.name
    in_scope = sorted(set(alias_map.values()))

    columns: list[dict] = []
    seen = set()
    for col in list(tree.find_all(exp.Column)):
        if col.table:
            real_table = alias_map.get(col.table)
            if real_table is None:
                raise Unparsed("unknown qualifier")
        else:
            owners = [t for t in in_scope if col.name in schema[t]]
            if len(owners) != 1:
                raise Unparsed("ambiguous or unknown column")
            real_table = owners[0]
        if col.name not in schema[real_table]:
            raise Unparsed("unknown column")
        role = _role_of(col)
        t_code, c_code = hasher.table(real_table), hasher.column(real_table, col.name)
        if role and (t_code, c_code, role) not in seen:
            seen.add((t_code, c_code, role))
            columns.append({"table": t_code, "col": c_code, "role": role})
        col.replace(exp.column(c_code))

    for t in list(tree.find_all(exp.Table)):
        t.replace(exp.to_table(hasher.table(t.name)))
    for a in list(tree.find_all(exp.Alias)):
        a.replace(a.this)
    tree = _replace_values(tree)
    return _check_output(tree.sql(comments=False), tree), columns


def hash_filter(text: str, hasher: Hasher, schema: Schema, alias_map: dict[str, str],
                default_table: str | None) -> tuple[str, list[str]]:
    """Hash one plan condition string (Filter, Index Cond, Hash Cond, ...).
    Returns (hashed expression, column codes). Raises Unparsed."""
    try:
        tree = sqlglot.parse_one(text, dialect="postgres")
    except Exception as e:
        raise Unparsed(f"parse failed: {type(e).__name__}") from None
    cols: list[str] = []
    in_plan = sorted(set(alias_map.values()))
    for col in list(tree.find_all(exp.Column)):
        if col.table:
            real_table = alias_map.get(col.table)
        elif default_table and col.name in schema.get(default_table, set()):
            real_table = default_table
        else:
            owners = [t for t in in_plan if col.name in schema.get(t, set())]
            real_table = owners[0] if len(owners) == 1 else None
        if real_table is None or col.name not in schema.get(real_table, set()):
            raise Unparsed("unresolvable column in plan condition")
        code = hasher.column(real_table, col.name)
        if code not in cols:
            cols.append(code)
        col.replace(exp.column(code))
    tree = _replace_values(tree)
    return _check_output(tree.sql(comments=False), tree), cols
