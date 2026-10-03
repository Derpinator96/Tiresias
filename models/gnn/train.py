"""REFERENCE training loop, not the delivered model. The trainer may replace it; whatever
trains the model must keep model.PlanGNN, features.FEATURE_VERSION and split.json, and
return weights/gnn.pt (state_dict) plus weights/meta.json. Settings from config gnn.*.

    python -m models.gnn.train [dataset_dir] [weights_dir]
"""
from __future__ import annotations

import gzip
import json
import sys
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


def graphs(rows: list[dict]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """(x, parent, y) for plans that ran; timed-out plans have no node labels."""
    return [(features.node_features(r["nodes"]), features.parents(r["nodes"]), features.targets(r["nodes"]))
            for r in rows if not r["timed_out"]]


def new_model() -> PlanGNN:
    return PlanGNN(features.N_FEATURES, int(cfg("gnn.hidden_size")), int(cfg("gnn.layers")), float(cfg("gnn.dropout")))


def loss_on(model, gs) -> torch.Tensor:
    x, p, _ = batch([(x, p) for x, p, _ in gs])
    y = torch.from_numpy(np.concatenate([y for *_, y in gs]))
    keep = ~torch.isnan(y)
    return torch.nn.functional.mse_loss(model(x, p)[keep], y[keep])


def train(dataset_dir: Path, weights_dir: Path, log=print) -> dict:
    torch.manual_seed(int(cfg("dataset.random_seed")))
    tr, va = graphs(load(dataset_dir, "train")), graphs(load(dataset_dir, "val"))
    model = new_model()
    opt = torch.optim.Adam(model.parameters(), lr=float(cfg("gnn.learning_rate")))
    bs, best, bad, best_state = int(cfg("gnn.batch_size")), float("inf"), 0, None
    rng = np.random.default_rng(0)
    for epoch in range(int(cfg("gnn.max_epochs"))):
        model.train()
        order = rng.permutation(len(tr))
        for i in range(0, len(tr), bs):
            opt.zero_grad()
            loss_on(model, [tr[j] for j in order[i:i + bs]]).backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            v = loss_on(model, va).item() if va else float("nan")
        if v < best:
            best, bad, best_state = v, 0, {k: t.clone() for k, t in model.state_dict().items()}
        else:
            bad += 1
            if bad >= int(cfg("gnn.patience")):
                break
        log(f"epoch {epoch}: val mse {v:.4f}")
    weights_dir.mkdir(parents=True, exist_ok=True)
    torch.save(best_state or model.state_dict(), weights_dir / "gnn.pt")
    meta = {"feature_version": features.FEATURE_VERSION, "n_features": features.N_FEATURES,
            "hidden_size": int(cfg("gnn.hidden_size")), "layers": int(cfg("gnn.layers")),
            "dropout": float(cfg("gnn.dropout")), "trained_on_plans": len(tr), "val_mse": best,
            "epochs": epoch + 1, "trained_by": "reference loop (models/gnn/train.py)"}
    (weights_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / cfg("gnn.dataset_dir")
    w = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / "models" / "gnn" / "weights"
    print(train(d, w))
