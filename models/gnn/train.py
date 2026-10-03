"""Training loop for the plan GNN. Whatever trains the model must keep model.PlanGNN,
features.FEATURE_VERSION and split.json, and return weights/gnn.pt (state_dict) plus
weights/meta.json. Settings from config gnn.*.

Loss: per-node MSE on log1p(self_ms) plus gnn.graph_loss_weight x MSE on the plan's total,
log1p(sum of expm1(node predictions)), which is exactly how evaluate.py and serving turn
node outputs into a plan runtime. Early stopping watches a validation q-error of that total
(gnn.early_stop_metric), not the node MSE. The output bias starts
at the mean node label, so the first epochs do not spend their steps climbing to the right
scale. Runs on CUDA when gnn.device allows it; the saved state_dict is moved to CPU, so it
loads the same in the CPU-only image.

    python -m models.gnn.train [dataset_dir] [weights_dir]
"""
from __future__ import annotations

import gzip
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

from common.config import REPO_ROOT, cfg
from models.gnn import features
from models.gnn.model import PlanGNN, batch


def load(dataset_dir: Path, part: str) -> list[dict]:
    split = set(json.loads((dataset_dir / "split.json").read_text())[part])
    with gzip.open(dataset_dir / "dataset.jsonl.gz", "rt", encoding="utf-8") as f:
        return [r for r in map(json.loads, f) if r["group"] in split]


def graphs(rows: list[dict]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    """(x, parent, y, total_ms) for plans that ran; timed-out plans have no node labels."""
    return [(features.node_features(r["nodes"]), features.parents(r["nodes"]), features.targets(r["nodes"]),
             float(r["total_ms"]))
            for r in rows if not r["timed_out"] and r["total_ms"] is not None]


def new_model() -> PlanGNN:
    return PlanGNN(features.N_FEATURES, int(cfg("gnn.hidden_size")), int(cfg("gnn.layers")), float(cfg("gnn.dropout")))


def pick_device() -> torch.device:
    want = str(cfg("gnn.device"))
    if want == "auto":
        want = "cuda" if torch.cuda.is_available() else "cpu"
    return torch.device(want)


def to_device(gs, device) -> tuple[torch.Tensor, ...]:
    """One batch on the device: features, parents, graph id per node, node labels, plan totals."""
    x, p, gid = batch([(x, p) for x, p, *_ in gs])
    y = torch.from_numpy(np.concatenate([y for _, _, y, _ in gs]))
    total = torch.tensor([t for *_, t in gs], dtype=torch.float32)
    return tuple(t.to(device) for t in (x, p, gid, y, total))


def plan_totals(node_log: torch.Tensor, gid: torch.Tensor, n_graphs: int, cap: float) -> torch.Tensor:
    """Plan runtime in ms: sum over its nodes of expm1(prediction), the evaluate.py rule.
    The clamp keeps expm1 finite; cap is log1p of the statement timeout in ms."""
    ms = torch.expm1(node_log.clamp(min=0.0, max=cap))
    return torch.zeros(n_graphs, device=node_log.device).index_add(0, gid, ms)


def loss_on(model, tensors, n_graphs: int, cap: float, graph_weight: float) -> torch.Tensor:
    x, p, gid, y, total = tensors
    out = model(x, p)
    keep = ~torch.isnan(y)
    node = torch.nn.functional.mse_loss(out[keep], y[keep])
    plan = torch.nn.functional.mse_loss(torch.log1p(plan_totals(out, gid, n_graphs, cap)), torch.log1p(total))
    return node + graph_weight * plan


def val_score(model, tensors, n_graphs: int, cap: float) -> dict:
    """Validation q-errors of the plan total. mean_log_q_error is the mean of log(q), which
    weighs the bad tail as well as the middle; median_q_error is what serving compares."""
    from models.gnn.evaluate import q_errors   # evaluate imports load() from here
    x, p, gid, _, total = tensors
    with torch.no_grad():
        pred = plan_totals(model(x, p), gid, n_graphs, cap)
    q = q_errors(pred.cpu().numpy(), total.cpu().numpy())
    return {"median_q_error": float(np.median(q)), "p95_q_error": float(np.percentile(q, 95)),
            "mean_log_q_error": float(np.mean(np.log(q)))}


def train(dataset_dir: Path, weights_dir: Path, log=print) -> dict:
    seed = int(cfg("dataset.random_seed"))
    torch.manual_seed(seed)
    device = pick_device()
    tr, va = graphs(load(dataset_dir, "train")), graphs(load(dataset_dir, "val"))
    cap = math.log1p(float(cfg("postgres.statement_timeout_plan_generation_s")) * 1000.0)
    graph_weight = float(cfg("gnn.graph_loss_weight"))
    model = new_model()
    labels = np.concatenate([y for _, _, y, _ in tr])
    with torch.no_grad():
        model.out[-1].bias.fill_(float(np.nanmean(labels)))
    model.to(device)
    opt = torch.optim.Adam(model.parameters(), lr=float(cfg("gnn.learning_rate")),
                           weight_decay=float(cfg("gnn.weight_decay")))
    val_t = to_device(va, device) if va else None
    bs, patience = int(cfg("gnn.batch_size")), int(cfg("gnn.patience"))
    stop_on = str(cfg("gnn.early_stop_metric"))
    best, best_epoch, bad, best_state, best_sc = float("inf"), -1, 0, None, {}
    rng = np.random.default_rng(seed)
    started = time.time()
    for epoch in range(int(cfg("gnn.max_epochs"))):
        model.train()
        order = rng.permutation(len(tr))
        for i in range(0, len(tr), bs):
            chunk = [tr[j] for j in order[i:i + bs]]
            opt.zero_grad()
            loss_on(model, to_device(chunk, device), len(chunk), cap, graph_weight).backward()
            opt.step()
        model.eval()
        sc = val_score(model, val_t, len(va), cap) if va else {}
        v = sc.get(stop_on, float("nan"))
        log(f"epoch {epoch}: val " + ", ".join(f"{k} {x:.4f}" for k, x in sc.items()))
        if v < best:
            best, best_epoch, bad, best_sc = v, epoch, 0, sc
            best_state = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break
    weights_dir.mkdir(parents=True, exist_ok=True)
    torch.save(best_state or {k: t.cpu() for k, t in model.state_dict().items()}, weights_dir / "gnn.pt")
    meta = {"feature_version": features.FEATURE_VERSION, "n_features": features.N_FEATURES,
            "hidden_size": int(cfg("gnn.hidden_size")), "layers": int(cfg("gnn.layers")),
            "dropout": float(cfg("gnn.dropout")), "trained_on_plans": len(tr), "early_stop_metric": stop_on,
            **{f"val_{k}": round(x, 4) for k, x in best_sc.items()},
            "best_epoch": best_epoch, "epochs": epoch + 1, "seed": seed, "device": device.type,
            "train_seconds": round(time.time() - started, 1),
            "trained_by": "models/gnn/train.py (node + plan-total loss)"}
    (weights_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / cfg("gnn.dataset_dir")
    w = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / "models" / "gnn" / "weights"
    print(train(d, w))
