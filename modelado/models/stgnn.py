"""GNN espacio-temporal para Tier 2 (ML_05) -- el elemento *wow* del TFM.

**GraphSAGE + GRU**, la opción más robusta con la ventana corta del proyecto
(~325 snapshots horarios, `NEXT_STEPS.md` §4):

1.  Por cada hora de la ventana se hacen `capas_gnn` pasos de *message
    passing* sobre el grafo urbano -> un embedding por nodo.
2.  Un GRU recorre la secuencia de embeddings de cada nodo -> estado final.
3.  Una cabeza lineal proyecta a `[N, n_horizontes, n_targets]`.

La capa `ConvGraphSAGE` está **implementada a mano** (media ponderada por
`edge_weight` vía `index_add`) en vez de usar `torch_geometric`: así
`edge_weight` queda en el grafo de autograd y `d(loss)/d(edge_weight)` da la
**importancia de aristas** que pide el ticket, y la única dependencia es
`torch` (CPU). Modelo pequeño y regularizado a propósito -- es una
demostración de metodología, no un SOTA (ver §7.4).
"""

from __future__ import annotations

import torch
from torch import nn


def _media_vecinos(
    h: torch.Tensor, edge_index: torch.Tensor, edge_weight: torch.Tensor, num_nodes: int
) -> torch.Tensor:
    """Media de los mensajes entrantes ponderada por `edge_weight`.
    `edge_index[0]` = origen, `edge_index[1]` = destino. `h` `[N, C]`."""
    src, dst = edge_index[0], edge_index[1]
    msg = h.index_select(0, src) * edge_weight.unsqueeze(-1)
    agg = torch.zeros(num_nodes, h.size(-1), dtype=h.dtype, device=h.device)
    agg = agg.index_add(0, dst, msg)
    deg = torch.zeros(num_nodes, dtype=h.dtype, device=h.device)
    deg = deg.index_add(0, dst, edge_weight).clamp_min(1e-6)
    return agg / deg.unsqueeze(-1)


class ConvGraphSAGE(nn.Module):
    """`h' = W_self h + W_vec · mean_w(vecinos)`. Sin self-loops en
    `edge_index` (el término propio es explícito)."""

    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.lin_self = nn.Linear(in_dim, out_dim)
        self.lin_vec = nn.Linear(in_dim, out_dim, bias=False)

    def forward(
        self, h: torch.Tensor, edge_index: torch.Tensor, edge_weight: torch.Tensor
    ) -> torch.Tensor:
        vec = _media_vecinos(h, edge_index, edge_weight, h.size(0))
        return self.lin_self(h) + self.lin_vec(vec)


class STGNN(nn.Module):
    def __init__(
        self,
        in_dim: int,
        *,
        hidden: int = 64,
        n_horizontes: int = 3,
        n_targets: int = 1,
        capas_gnn: int = 2,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.n_horizontes = n_horizontes
        self.n_targets = n_targets
        dims = [in_dim] + [hidden] * capas_gnn
        self.convs = nn.ModuleList(
            ConvGraphSAGE(dims[i], dims[i + 1]) for i in range(capas_gnn)
        )
        self.act = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.gru = nn.GRU(hidden, hidden, batch_first=True)
        self.cabeza = nn.Linear(hidden, n_horizontes * n_targets)

    def _encode_hora(
        self, x: torch.Tensor, edge_index: torch.Tensor, edge_weight: torch.Tensor
    ) -> torch.Tensor:
        h = x
        for conv in self.convs:
            h = self.dropout(self.act(conv(h, edge_index, edge_weight)))
        return h  # [N, hidden]

    def forward(
        self,
        x_seq: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: torch.Tensor,
    ) -> torch.Tensor:
        """`x_seq` `[L, N, F]` (una muestra) -> `[N, n_horizontes, n_targets]`.
        El grafo (`edge_index`, `edge_weight`) es fijo en la ventana."""
        emb = torch.stack(
            [self._encode_hora(x_seq[t], edge_index, edge_weight) for t in range(x_seq.size(0))],
            dim=1,
        )  # [N, L, hidden]
        salida, _ = self.gru(emb)
        y = self.cabeza(salida[:, -1, :])  # [N, H*T]
        return y.view(-1, self.n_horizontes, self.n_targets)
