"""Plan generation CLI, run in the bench container (make plans-load, plans-sample, plans).

    python -m db.plangen load [--force]   load dsb, tpch and the QuickMart copy into pg-bench
    python -m db.plangen sample           the early sample (plan_generation.early_sample_size)
    python -m db.plangen run              every template x parameter set x index setup
    python -m db.plangen dedupe           plans_raw.jsonl -> plans.jsonl and summary.json
    python -m db.plangen export [sample]  plans.jsonl (or the sample) -> data/gnn/ dataset + split
"""
from __future__ import annotations

import sys
import time

from common.config import cfg
from db.plangen import load, run


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else ""
    if cmd == "load":
        load.load_all(force="--force" in argv, log=log)
        return
    if cmd == "dedupe":
        d = run.out_dir()
        run.dedupe(d / "plans_raw.jsonl", d / "plans.jsonl", d / "summary.json", log=log)
        return
    if cmd == "export":
        from db.plangen import export
        n = int(cfg("plan_generation.early_sample_size"))
        export.export(*export.default_paths(f"sample_{n}.jsonl" if "sample" in argv else "plans.jsonl"), log=log)
        return
    if cmd not in ("sample", "run"):
        sys.exit(__doc__)
    wl = run.workload()
    run.check_setup_counts(wl)
    log("templates: " + ", ".join(f"{db} {len(w['templates'])}" for db, w in wl.items()))
    d = run.out_dir()
    if cmd == "sample":
        n = int(cfg("plan_generation.early_sample_size"))
        run.execute(run.sample_plan(wl, n), d / f"sample_{n}.jsonl", log=log)
    else:
        run.execute(run.full_plan(wl), d / "plans_raw.jsonl", log=log)
        run.dedupe(d / "plans_raw.jsonl", d / "plans.jsonl", d / "summary.json", log=log)


if __name__ == "__main__":
    main(sys.argv[1:])
