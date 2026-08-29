"""Tensores de grafo por hora para el GNN espacio-temporal (ML_05, Tier 2).

Convierte el panel horario de `ML_01` + una lista de aristas del grafo urbano
en la secuencia de snapshots `(X, Y, M)` que consume `modelado/models/stgnn.py`:

- `X`  `[T_pasos, N, F]`  -- features de nodo por hora (las mismas del panel).
- `Y`  `[T_pasos, N, H]`  -- target por nodo y horizonte (`target_h{1,3,6}`).
- `M`  `[T_pasos, N, H]`  -- máscara booleana (target finito / nodo observado).

Todo son funciones puras sobre `pandas`/`numpy` -- testables sin credenciales
ni `torch` (`modelado/tests/test_ml05.py`). El grafo se pasa como lista de
aristas o se deriva de las coordenadas del propio panel (`edges_desde_coords`,
k-NN con núcleo gaussiano sobre la distancia -- el criterio habitual para
redes de sensores dispersas). El entry point que entrena contra el panel real
y, si hay Neo4j, contra las aristas `PROXIMO_A` de verdad es
`modelado/training/train_stgnn.py`.

Regla de oro de `ML_01` intacta: `X[t]` solo lleva features con
`known_at <= t`; `Y[t]` es `shift(-h)` y va enmascarado, nunca entra como
feature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGETS_STGNN = ("target_h1", "target_h3", "target_h6")
_NO_FEATURE = {"entity_id", "ts", "lat", "lon"}

_RADIO_TIERRA_M = 6_371_000.0


def columnas_features(panel: pd.DataFrame) -> "list[str]":
    """Columnas numéricas de `panel` que son features de nodo: todo menos
    ids, coordenadas y los `target_h*`. Orden estable (el del panel)."""
    return [
        c
        for c in panel.columns
        if c not in _NO_FEATURE
        and not c.startswith("target_h")
        and pd.api.types.is_numeric_dtype(panel[c])
    ]


def indice_nodos(panel: pd.DataFrame) -> "dict[str, int]":
    """`entity_id -> 0..N-1`, ordenado alfabéticamente (determinista)."""
    return {eid: i for i, eid in enumerate(sorted(panel["entity_id"].astype(str).unique()))}


def coordenadas_por_nodo(panel: pd.DataFrame, node_index: "dict[str, int]") -> np.ndarray:
    """`[N, 2]` lat/lon por nodo (mediana de las filas de esa entidad -- las
    filas de hueco del reindex horario traen NaN). NaN si la entidad no tiene
    ninguna coordenada."""
    coords = np.full((len(node_index), 2), np.nan, dtype="float64")
    med = panel.groupby(panel["entity_id"].astype(str))[["lat", "lon"]].median()
    for eid, i in node_index.items():
        if eid in med.index:
            coords[i] = med.loc[eid, ["lat", "lon"]].to_numpy()
    return coords


def _haversine_m(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Matriz de distancias (m) entre dos conjuntos de puntos lat/lon en
    grados. `a` `[n,2]`, `b` `[m,2]` -> `[n,m]`."""
    la1 = np.radians(a[:, 0])[:, None]
    lo1 = np.radians(a[:, 1])[:, None]
    la2 = np.radians(b[:, 0])[None, :]
    lo2 = np.radians(b[:, 1])[None, :]
    dla = la2 - la1
    dlo = lo2 - lo1
    h = np.sin(dla / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin(dlo / 2) ** 2
    return 2 * _RADIO_TIERRA_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def edges_desde_coords(
    coords: np.ndarray,
    *,
    k: int = 8,
    radio_m: "float | None" = None,
    sigma_m: "float | None" = None,
) -> "tuple[np.ndarray, np.ndarray]":
    """Grafo de proximidad a partir de `[N,2]` lat/lon.

    - `radio_m`: conecta pares a <= esa distancia. Si es `None`, k-NN: cada
      nodo con sus `k` vecinos más cercanos.
    - Se simetriza (unión). Sin self-loops (el modelo lleva término propio).
    - Peso = `exp(-(d/sigma)^2)`; `sigma` = mediana de las distancias de las
      aristas si no se da.

    Devuelve `(edge_index [2,E], edge_weight [E])`, `edge_index[0]` = origen
    del mensaje, `edge_index[1]` = destino.
    """
    n = len(coords)
    if n == 0:
        return np.zeros((2, 0), dtype="int64"), np.zeros(0, dtype="float64")
    d = _haversine_m(coords, coords)
    np.fill_diagonal(d, np.inf)
    finito = np.isfinite(d)

    pares: "set[tuple[int, int]]" = set()
    if radio_m is not None:
        for i, j in zip(*np.where(finito & (d <= radio_m))):
            pares.add((int(min(i, j)), int(max(i, j))))
    else:
        kk = min(k, n - 1)
        for i in range(n):
            fila = d[i].copy()
            fila[~finito[i]] = np.inf
            vecinos = np.argsort(fila)[:kk]
            for j in vecinos:
                if np.isfinite(fila[j]):
                    pares.add((int(min(i, j)), int(max(i, j))))

    if not pares:
        return np.zeros((2, 0), dtype="int64"), np.zeros(0, dtype="float64")

    ii = np.array([p[0] for p in sorted(pares)], dtype="int64")
    jj = np.array([p[1] for p in sorted(pares)], dtype="int64")
    dist = d[ii, jj]
    if sigma_m is None:
        sigma_m = float(np.median(dist)) or 1.0
    w = np.exp(-((dist / sigma_m) ** 2))

    # no dirigido -> las dos orientaciones
    src = np.concatenate([ii, jj])
    dst = np.concatenate([jj, ii])
    weight = np.concatenate([w, w])
    return np.vstack([src, dst]).astype("int64"), weight.astype("float64")


def edges_desde_lista(
    aristas: "list[tuple[str, str, float]]",
    node_index: "dict[str, int]",
    *,
    sigma_m: "float | None" = None,
) -> "tuple[np.ndarray, np.ndarray]":
    """Aristas `(entity_id_a, entity_id_b, distancia_m)` -- p. ej. las
    `PROXIMO_A` de Neo4j -- a `(edge_index, edge_weight)`. Se ignoran las que
    referencian nodos fuera de `node_index`. Simétrico, peso gaussiano."""
    pares: "dict[tuple[int, int], float]" = {}
    for a, b, dist in aristas:
        if a not in node_index or b not in node_index or a == b:
            continue
        i, j = node_index[a], node_index[b]
        clave = (min(i, j), max(i, j))
        pares[clave] = min(pares.get(clave, float("inf")), float(dist))
    if not pares:
        return np.zeros((2, 0), dtype="int64"), np.zeros(0, dtype="float64")
    claves = sorted(pares)
    ii = np.array([c[0] for c in claves], dtype="int64")
    jj = np.array([c[1] for c in claves], dtype="int64")
    dist = np.array([pares[c] for c in claves], dtype="float64")
    if sigma_m is None:
        sigma_m = float(np.median(dist)) or 1.0
    w = np.exp(-((dist / sigma_m) ** 2))
    src = np.concatenate([ii, jj])
    dst = np.concatenate([jj, ii])
    weight = np.concatenate([w, w])
    return np.vstack([src, dst]).astype("int64"), weight.astype("float64")


def construir_snapshots(
    panel: pd.DataFrame,
    node_index: "dict[str, int]",
    feature_cols: "list[str]",
    *,
    target_cols: "tuple[str, ...]" = TARGETS_STGNN,
) -> "dict[str, np.ndarray | list]":
    """Panel horario -> `(orden_ts, X, Y, M)`.

    `X[t, n, :]` son las `feature_cols` de la entidad `n` a la hora
    `orden_ts[t]` (0 y `M`=... donde no hay fila); `Y[t, n, h]` es
    `target_cols[h]`; `M[t, n, h]` es `True` si ese target es finito.
    """
    n_nodos = len(node_index)
    horas = pd.date_range(panel["ts"].min(), panel["ts"].max(), freq="h")
    t_idx = {ts: i for i, ts in enumerate(horas)}
    n_feat, n_h = len(feature_cols), len(target_cols)

    X = np.zeros((len(horas), n_nodos, n_feat), dtype="float32")
    Y = np.zeros((len(horas), n_nodos, n_h), dtype="float32")
    M = np.zeros((len(horas), n_nodos, n_h), dtype=bool)

    eid = panel["entity_id"].astype(str)
    fila_nodo = eid.map(node_index).to_numpy()
    fila_hora = panel["ts"].map(t_idx).to_numpy()
    ok = ~pd.isna(fila_nodo) & ~pd.isna(fila_hora)
    fn = fila_nodo[ok].astype("int64")
    fh = fila_hora[ok].astype("int64")

    feat = panel.loc[ok, feature_cols].to_numpy(dtype="float32")
    feat = np.nan_to_num(feat, nan=0.0, posinf=0.0, neginf=0.0)
    X[fh, fn, :] = feat

    tgt = panel.loc[ok, list(target_cols)].to_numpy(dtype="float32")
    Y[fh, fn, :] = np.nan_to_num(tgt, nan=0.0)
    M[fh, fn, :] = np.isfinite(tgt)

    return {"orden_ts": list(horas), "X": X, "Y": Y, "M": M}


def ventanas_secuencia(
    snapshots: "dict[str, np.ndarray | list]", *, longitud: int = 12
) -> "dict[str, np.ndarray | list]":
    """Ventanas deslizantes para el GRU. Una muestra en el paso `i`
    (`i >= longitud-1`): `Xseq = X[i-longitud+1 : i+1]` (`[L, N, F]`),
    objetivo `Y[i]` / `M[i]`, hora objetivo `orden_ts[i]`.

    Devuelve `Xseq [S, L, N, F]`, `Y [S, N, H]`, `M [S, N, H]`, `ts_objetivo`.
    """
    X, Y, M = snapshots["X"], snapshots["Y"], snapshots["M"]
    ts = snapshots["orden_ts"]
    t = X.shape[0]
    if t < longitud:
        raise ValueError(f"serie de {t} pasos < longitud de ventana {longitud}")
    idx = np.arange(longitud - 1, t)
    Xseq = np.stack([X[i - longitud + 1 : i + 1] for i in idx]).astype("float32")
    return {
        "Xseq": Xseq,
        "Y": Y[idx].astype("float32"),
        "M": M[idx],
        "ts_objetivo": [ts[i] for i in idx],
    }
