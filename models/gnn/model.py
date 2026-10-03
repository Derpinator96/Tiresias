"""Plan GNN (doc, Component 3 and Detailed component specs): attention message passing up
the plan tree, child to parent, predicting each node's log1p(self_ms).

Plain PyTorch, no PyTorch Geometric: plans are tiny trees, and a plain state_dict loads the
same on Colab and in the pinned image (doc's own fallback for PyG install trouble).
Single attention head per layer; the doc gives no head count.
"""
from __future__ import annotations

import numpy as np
import torch
from torch import nn


class TreeAttention(nn.Module):
    """One GAT-style layer: each node attends over itself and its children."""

    def __init__(self, hidden: int):
        super().__init__()
        self.w = nn.Linear(hidden, hidden, bias=False)
        self.a_src = nn.Parameter(torch.randn(hidden) * 0.1)
        self.a_dst = nn.Parameter(torch.randn(hidden) * 0.1)

    def forward(self, h: torch.Tensor, parent: torch.Tensor) -> torch.Tensor:
        n = h.size(0)
        idx = torch.arange(n, device=h.device)
        has = parent >= 0
        src = torch.cat([idx, idx[has]])          # self loops, then child -> parent edges
        dst = torch.cat([idx, parent[has]])
        z = self.w(h)
        e = nn.functional.leaky_relu((z[src] * self.a_src).sum(-1) + (z[dst] * self.a_dst).sum(-1), 0.2)
        top = torch.full((n,), -torch.inf, device=h.device).scatter_reduce(0, dst, e, "amax")
        w = (e - top[dst]).exp()
        alpha = w / torch.zeros(n, device=h.device).index_add(0, dst, w)[dst]
        return torch.zeros_like(z).index_add(0, dst, alpha.unsqueeze(-1) * z[src])


class PlanGNN(nn.Module):
    def __init__(self, n_features: int, hidden: int, layers: int, dropout: float):
        super().__init__()
        self.inp = nn.Linear(n_features, hidden)
        self.layers = nn.ModuleList(TreeAttention(hidden) for _ in range(layers))
        self.drop = nn.Dropout(dropout)
        self.out = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, x: torch.Tensor, parent: torch.Tensor) -> torch.Tensor:
        h = torch.relu(self.inp(x))
        for layer in self.layers:
            h = h + self.drop(torch.relu(layer(h, parent)))
        return self.out(h).squeeze(-1)


def batch(graphs: list[tuple[np.ndarray, np.ndarray]]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Concatenate (x, parent) graphs; parent indices are offset; returns graph id per node."""
    xs, ps, gid, off = [], [], [], 0
    for g, (x, p) in enumerate(graphs):
        xs.append(x)
        ps.append(np.where(p >= 0, p + off, -1))
        gid.append(np.full(len(x), g))
        off += len(x)
    return (torch.from_numpy(np.concatenate(xs)), torch.from_numpy(np.concatenate(ps)),
            torch.from_numpy(np.concatenate(gid)))
