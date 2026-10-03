"""Gateway service: ingestion, the private template registry, resolving and dehashing.

Everything here runs on the private side. The api module decides what leaves, and every
response bound for the AI side goes through `send_to_ai`, which scans and ledgers it.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass, field

import psycopg
import yaml

from common.config import cfg
from contracts.validate import validate
from db import canaries
from gateway import catalog as catalog_mod
from gateway.canary_scan import Scanner
from gateway.hashing import Hasher
from gateway.ingest import plans as plans_mod
from gateway.ingest import stats as stats_mod
from gateway.ingest import statements as statements_mod
from gateway.keys import hmac_key
from gateway.ledger import Ledger

RESOLVER_MAP = os.path.join(os.path.dirname(__file__), "resolver_map.yaml")
CODE_RE = re.compile(r"\b([tciq])_[0-9a-f]{8}\b")


class Blocked(Exception):
    """A payload hit a canary and was not sent."""

    def __init__(self, entry: dict):
        super().__init__("payload blocked by canary scan")
        self.entry = entry


@dataclass
class Snapshot:
    """One consistent read of pg-prod. Private: holds real names and literals."""
    catalog: catalog_mod.Catalog
    templates: list[statements_mod.Template]
    withheld: int
    plans: list[plans_mod.LoggedPlan] = field(default_factory=list)

    def template(self, template_id: str) -> statements_mod.Template | None:
        return next((t for t in self.templates if t.template_id == template_id), None)

    def plans_for(self, template_id: str) -> list[plans_mod.LoggedPlan]:
        t = self.template(template_id)
        ids = set(t.queryids) if t else set()
        return [p for p in self.plans if p.query_id in ids]


class Gateway:
    def __init__(self, prod_dsn: str, log_dir: str, ledger_path: str | None = None):
        self.prod_dsn = prod_dsn
        self.log_dir = log_dir
        self.hasher = Hasher(hmac_key())
        self.scanner = Scanner()
        self.ledger = Ledger(ledger_path or cfg("gateway.ledger_path"))

    # ---- ingestion -------------------------------------------------------------------
    def snapshot(self) -> Snapshot:
        with psycopg.connect(self.prod_dsn, autocommit=True) as conn:
            cat = catalog_mod.read(conn)
            schema = cat.schema()
            for t, cols in schema.items():           # fill the vault for dehashing
                self.hasher.table(t)
                for c in cols:
                    self.hasher.column(t, c)
            templates, withheld = statements_mod.read(conn, self.hasher, schema)
        return Snapshot(cat, templates, withheld, plans_mod.read_log(self.log_dir))

    def slow_templates(self, snap: Snapshot) -> list[dict]:
        threshold = float(cfg("workload.slow_query_ms"))
        return [t.hashed for t in snap.templates if t.hashed["mean_ms"] >= threshold]

    def hashed_plans(self, snap: Snapshot, template_id: str) -> list[dict]:
        schema = snap.catalog.schema()
        logged = snap.plans_for(template_id)[-int(cfg("gateway.plans_per_template")):]
        out = []
        for p in reversed(logged):                   # newest first
            plan_id = self.hasher.opaque("p", f"auto_explain:{p.order_key}")
            out.append(plans_mod.hash_plan(p.plan, plan_id=plan_id, template_id=template_id,
                                           setup_id="s_baseline", source="auto_explain",
                                           hasher=self.hasher, schema=schema))
        return out

    # ---- what-if ----------------------------------------------------------------------
    def decode_config(self, config: dict) -> list[tuple[str, list[str]]]:
        """Real (table, [columns]) for each add_index action. Unknown codes raise KeyError.
        Rewrite actions are read by decode_rewrites; partition is not simulated yet."""
        out = []
        for a in config["actions"]:
            if a["type"] == "rewrite":
                continue
            if a["type"] != "add_index":
                raise ValueError(f"action {a['type']} is not simulated yet")
            table = self.hasher.vault[a["table"]]["name"]
            cols = []
            for c in a["columns"]:
                t, col = self.hasher.vault[c]["name"].split(".", 1)
                if t != table:
                    raise ValueError("index columns must belong to the index's table")
                cols.append(col)
            out.append((table, cols))
        return out

    @staticmethod
    def decode_rewrites(config: dict) -> dict[str, str]:
        """{template_id: rule_id} for each rewrite action."""
        return {a["template_id"]: a["rule_id"] for a in config["actions"] if a["type"] == "rewrite"}

    def rewritten_queries(self, snap: Snapshot, config: dict) -> dict[str, str]:
        """Real rewritten SQL for each template the config rewrites. Raises ValueError when a
        rule does not apply to the template's logged query (its shape or values)."""
        from gateway import rewrite_rules as rr
        out = {}
        for tid, rule in self.decode_rewrites(config).items():
            if snap.template(tid) is None or rule not in rr.RULES:
                raise ValueError("unknown template or rule")
            query, generic = self.sample_queries(snap, [tid])[tid]
            if generic:
                raise ValueError("template has no logged query to rewrite")
            try:
                out[tid] = rr.rewrite(query, rule)
            except rr.NotApplicable as e:
                raise ValueError(str(e)) from None
        return out

    def rewrite_candidates(self, snap: Snapshot) -> list[dict]:
        """Rules whose shape matches each slow template's hashed SQL, with the rewritten hashed
        SQL (values as `?`). Shape only: values are checked when the rewrite is verified."""
        from gateway import rewrite_rules as rr
        out = []
        for t in self.slow_templates(snap):
            for rule in rr.matching(t["sql"]):
                out.append({"template_id": t["template_id"], "rule_id": rule, "description": rr.RULES[rule].description,
                            "sql": rr.rewrite_shape(t["sql"], rule), "label": rr.LABEL})
        return out

    def check_rewrite(self, snap: Snapshot, template_id: str, rule_id: str, twin_dsn: str) -> dict:
        """Rewrite contract object: VeriEQL on the real SQL plus a result checksum on the twin.
        Verified = VeriEQL pass and checksums match; TestedOnly = VeriEQL could not decide
        (unsupported or not run) and checksums match; Rejected = either check failed."""
        from db.sandbox import checksum, twin_measure, verieql
        from gateway import rewrite_rules as rr
        config = {"actions": [{"type": "rewrite", "template_id": template_id, "rule_id": rule_id}]}
        rewritten = self.rewritten_queries(snap, config)[template_id]
        original = self.sample_queries(snap, [template_id])[template_id][0]
        v = verieql.check(original, rewritten, snap.catalog)
        mapping = twin_measure.load_map()
        c = checksum.queries_match(twin_dsn, twin_measure.map_query(original, mapping), twin_measure.map_query(rewritten, mapping))
        checks = {"verieql": v["result"], "checksum": "match" if c["match"] else "mismatch"}
        if v["result"] == "fail" or not c["match"]:
            status = "Rejected"
        elif v["result"] == "pass":
            status = "Verified"
        else:
            status = "TestedOnly"
        hashed = next(t["sql"] for t in self.slow_templates(snap) if t["template_id"] == template_id)
        return {"rewrite_id": self.hasher.opaque("rw", f"{template_id}:{rule_id}"), "template_id": template_id,
                "rule_id": rule_id, "sql": rr.rewrite_shape(hashed, rule_id), "status": status, "checks": checks}

    def sample_queries(self, snap: Snapshot, template_ids: list[str]) -> dict[str, tuple[str, bool]]:
        """A runnable query per template: the latest logged query with its real literals, or
        the normalized $n text planned generically. Private: never sent."""
        out = {}
        for tid in template_ids:
            logged = snap.plans_for(tid)
            if logged and logged[-1].query_text:
                out[tid] = (logged[-1].query_text, False)
            else:
                out[tid] = (snap.template(tid).normalized_sql, True)
        return out

    def simulate_hypopg(self, snap: Snapshot, config: dict) -> dict:
        from db.sandbox import hypopg
        from gateway.rounding import round_sig
        indexes = self.decode_config(config)
        tids = [t["template_id"] for t in self.slow_templates(snap)]
        queries = self.sample_queries(snap, tids)
        for tid, q in self.rewritten_queries(snap, config).items():
            queries[tid] = (q, False)
        result = hypopg.explain_with_indexes(self.prod_dsn, indexes, queries)
        schema = snap.catalog.schema()
        setup = "s_" + config["config_id"]
        plans = [plans_mod.hash_plan(p, plan_id=self.hasher.opaque("p", f"hypopg:{config['config_id']}:{tid}"),
                                     template_id=tid, setup_id=setup, source="hypopg",
                                     hasher=self.hasher, schema=schema)
                 for tid, p in result.plans.items()]
        return {"plans": plans, "index_storage_mb": round_sig(result.index_bytes / 2**20)}

    def simulate_twin(self, snap: Snapshot, config: dict, twin_dsn: str) -> tuple[dict, dict]:
        """Measure a Config on the twin. Returns (SimResult, plan agreement per template).
        Only templates with a logged literal query can be replayed; generic plans cannot run."""
        from db.sandbox import twin_measure
        from gateway.rounding import round_ms, round_sig
        indexes = self.decode_config(config)
        tids = [t["template_id"] for t in self.slow_templates(snap)]
        runnable = {tid: q for tid, (q, generic) in self.sample_queries(snap, tids).items() if not generic}
        if not runnable:
            raise ValueError("no slow template has a logged query to replay")
        r = twin_measure.measure(self.prod_dsn, twin_dsn, indexes, runnable, self.rewritten_queries(snap, config))
        sim = {
            "config_id": config["config_id"],
            "source": "twin",
            "templates": [{"template_id": tid, "before_ms": round_ms(r.before_ms[tid]), "after_ms": round_ms(r.after_ms[tid])}
                          for tid in runnable],
            "write_ms_delta": round_ms(r.write_ms_delta),
            "storage_mb_delta": round_sig(r.storage_mb),
            "runs": r.runs,
        }
        return sim, r.plan_agreement

    def column_meta(self, snap: Snapshot) -> list[dict]:
        roles = {(c["col"], c["role"]) for t in snap.templates for c in t.hashed["columns"]}
        with psycopg.connect(self.prod_dsn, autocommit=True) as conn:
            return stats_mod.column_meta(conn, snap.catalog, self.hasher, roles)

    def table_meta(self, snap: Snapshot) -> list[dict]:
        with psycopg.connect(self.prod_dsn, autocommit=True) as conn:
            return stats_mod.table_meta(conn, snap.catalog, self.hasher)

    # ---- the only way out --------------------------------------------------------------
    def send_to_ai(self, contract: str | None, payload) -> bytes:
        """Validate, scan and ledger a payload bound for the AI side. Raises Blocked on a hit."""
        if contract:
            for item in (payload if isinstance(payload, list) else [payload]):
                validate(contract, item)
        body = json.dumps(payload).encode("utf-8")
        entry = self.ledger.record("ai", body, self.scanner.scan(body.decode("utf-8")))
        if entry["verdict"] == "block":
            raise Blocked(entry)
        return body

    def check_outbound(self, body: str) -> dict:
        """POST /v1/ledger/outbound: scan an LLM request body that ai is about to send."""
        return self.ledger.record("llm", body.encode("utf-8"), self.scanner.scan(body))

    def negative_control(self) -> dict:
        """Scan what would leave if the gateway were switched off: the raw query texts and raw
        auto_explain messages, unhashed and unstripped. Goes to the local scanner only."""
        with psycopg.connect(self.prod_dsn, autocommit=True) as conn:
            texts = [r[0] for r in conn.execute("SELECT query FROM pg_stat_statements")]
        raw = "\n".join(texts + [json.dumps(p.plan) for p in plans_mod.read_log(self.log_dir)])
        return self.ledger.record("local_scanner", raw.encode("utf-8"), self.scanner.scan(raw))

    # ---- DBA side ----------------------------------------------------------------------
    def resolve(self, question: str, snap: Snapshot) -> dict:
        """Map the DBA's question to template IDs locally. The question never leaves."""
        with open(RESOLVER_MAP, encoding="utf-8") as f:
            entries = yaml.safe_load(f)["dashboards"]
        q = question.lower()
        scores: dict[str, float] = {}
        for entry in entries:
            if any(p in q for p in entry["phrases"]):
                for t in snap.templates:
                    if t.normalized_sql == entry["query_pattern"]:
                        scores[t.template_id] = scores.get(t.template_id, 0) + 2
        for table in snap.catalog.columns:
            if re.search(rf"\b{re.escape(table)}\b", q) or re.search(rf"\b{re.escape(table.rstrip('s'))}\b", q):
                for t in snap.templates:
                    if re.search(rf"\b{re.escape(table)}\b", t.normalized_sql):
                        scores[t.template_id] = scores.get(t.template_id, 0) + 1
        ranked = sorted(scores, key=lambda k: -scores[k])[: int(cfg("gateway.resolver_top_templates"))]
        return {"question_id": "qn_" + secrets.token_hex(4), "template_ids": ranked,
                "question_had_canary": bool(self.scanner.scan(question))}

    def dehash(self, text: str, snap: Snapshot) -> str:
        names = {t.template_id: t.normalized_sql for t in snap.templates}
        limit = int(cfg("gateway.dehash_query_chars"))

        def real(m: re.Match) -> str:
            code = m.group(0)
            if code in names:
                sql = names[code]
                return f'query "{sql[:limit]}{"..." if len(sql) > limit else ""}"'
            entry = self.hasher.vault.get(code)
            if entry is None:
                return code
            return entry["name"].split(".", 1)[1] if entry["kind"] == "column" else entry["name"]
        return CODE_RE.sub(real, text)


def all_canary_ids() -> list[str]:
    return [c.canary_id for c in canaries.ALL]
