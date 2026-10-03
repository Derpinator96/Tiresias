"""Read QuickMart's catalog on pg-prod: tables, columns, types, keys, indexes. Private side."""
from __future__ import annotations

from dataclasses import dataclass, field

import psycopg


@dataclass
class Catalog:
    columns: dict[str, dict[str, str]] = field(default_factory=dict)   # table -> col -> data_type
    nullable: set[tuple[str, str]] = field(default_factory=set)
    pk: set[tuple[str, str]] = field(default_factory=set)
    fk: set[tuple[str, str]] = field(default_factory=set)
    indexed: set[tuple[str, str]] = field(default_factory=set)
    # index name -> (table, [columns in order])
    indexes: dict[str, tuple[str, list[str]]] = field(default_factory=dict)

    def schema(self) -> dict[str, set[str]]:
        return {t: set(cols) for t, cols in self.columns.items()}


def read(conn: psycopg.Connection) -> Catalog:
    cat = Catalog()
    for t, c, typ, nul in conn.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position"""):
        cat.columns.setdefault(t, {})[c] = typ
        if nul == "YES":
            cat.nullable.add((t, c))
    for t, c, kind in conn.execute("""
            SELECT con.conrelid::regclass::text, a.attname, con.contype
            FROM pg_constraint con
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
            WHERE con.connamespace = 'public'::regnamespace AND con.contype IN ('p', 'f')"""):
        (cat.pk if kind == "p" else cat.fk).add((t, c))
    for idx, t, cols in conn.execute("""
            SELECT i.relname, c.relname,
                   array_agg(a.attname ORDER BY array_position(ix.indkey::int2[], a.attnum))
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class c ON c.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY (ix.indkey)
            WHERE n.nspname = 'public'
            GROUP BY i.relname, c.relname"""):
        cat.indexes[idx] = (t, list(cols))
        cat.indexed.update((t, col) for col in cols)
    return cat
