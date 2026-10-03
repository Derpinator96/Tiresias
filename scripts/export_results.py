"""make export: write site/results.json from the latest passing e2e run (runs/latest.json).

Refuses to write anything if no passing run exists: the public results page must show only
numbers from a real run. Each number carries its source and its assumption, next to it.
Also records the git commit the run was made from (read from .git directly, because the
Python image has no git binary).

    python -m scripts.export_results
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from common.config import REPO_ROOT, cfg

RUN = REPO_ROOT / "runs" / "latest.json"
OUT = REPO_ROOT / "site" / "results.json"


def git_commit(repo: Path = REPO_ROOT) -> str:
    git = repo / ".git"
    head = (git / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head                                     # detached HEAD holds the hash itself
    ref = head[5:]
    loose = git / ref
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    packed = git / "packed-refs"
    if packed.exists():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
    raise RuntimeError(f"cannot resolve {ref}")


def build(run: dict, commit: str) -> dict:
    tw, se, pv, ds = run["twin"], run["search"], run["privacy"], run["dataset"]
    scale = f"{ds['hero_table_rows']:,}-row demo table (rounded to 2 significant figures), not production size"
    twin = f"measured on the statistical twin (synthetic rows from pg_stats, no column correlations yet), {scale}, median of {tw['runs']} warm runs"
    return {
        "run_id": run["run_id"],
        "finished_at": run["finished_at"],
        "git_commit": commit,
        "dataset": {"hero_table_rows": ds["hero_table_rows"], "hero_table_size_mb": ds["hero_table_size_mb"],
                    "assumption": "synthetic retail data generated for the demo; sizes rounded to 2 significant figures"},
        "results": [
            {"name": "Hero query before the index", "value": tw["before_ms"], "unit": "ms", "source": "twin measurement", "assumption": twin},
            {"name": "Hero query after the recommended index", "value": tw["after_ms"], "unit": "ms", "source": "twin measurement", "assumption": twin},
            {"name": "Speedup", "value": tw["speedup_pct"], "unit": "%", "source": "computed from the two measurements above", "assumption": twin},
            {"name": "Index storage", "value": tw["storage_mb"], "unit": "MB", "source": "pg_relation_size on the twin", "assumption": scale},
            {"name": "Result checksum with the index", "value": "match" if tw["checksum_match"] else "mismatch", "unit": "",
             "source": "MD5 of sorted result rows on the twin", "assumption": "checksum only; SQL equivalence checking (VeriEQL) is not built yet"},
            {"name": "Predicted time before", "value": se["predicted_before_ms"], "unit": "ms", "source": "search prediction",
             "assumption": f"{se['estimator_label']}; {se['label']}; predictions rank candidates and are not results"},
            {"name": "Predicted time after", "value": se["predicted_after_ms"], "unit": "ms", "source": "search prediction",
             "assumption": f"{se['estimator_label']}; {se['label']}; predictions rank candidates and are not results"},
            {"name": "Payloads sent to the AI side in this run", "value": pv["payloads"], "unit": "", "source": "payload ledger",
             "assumption": "AI-facing API responses plus LLM request bodies, each scanned before leaving"},
            {"name": "Canary hits in those payloads", "value": pv["canary_hits"], "unit": "", "source": "canary scanner",
             "assumption": f"{pv['canaries_planted']} canary placements; exact and 6-character fragment matching"},
            {"name": "LLM tool calls", "value": run["llm"]["tool_calls"], "unit": "", "source": "agent log",
             "assumption": f"{run['llm']['provider']} {run['llm']['model']}, temperature {cfg('llm.temperature')}"},
            {"name": "Numbers in the answer checked against tool results", "value": run["llm"]["numbers_checked"], "unit": "",
             "source": "number checker", "assumption": "an answer with any unmatched number is blocked"},
        ],
        "not_built": ["GNN cost model (Postgres cost estimates stand in)", "Q-learning (greedy search stands in)",
                      "twin column correlations", "write-cost measurement", "VeriEQL", "adversarial leak test",
                      "queries Q2 to Q4", "air-gapped mode"],
    }


def main() -> int:
    if not RUN.exists():
        print(f"no passing end-to-end run at {RUN}: run make e2e first. results.json not written.")
        return 1
    out = build(json.loads(RUN.read_text(encoding="utf-8")), git_commit())
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} for {out['run_id']} at commit {out['git_commit'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
