"""Previsión desde los modelos **de grafo** (STGNN de `ML_05`), servidos por
ONNX sin `torch` en runtime (`FIL_20` + `FIL_26` + `FIL_31`).

A diferencia de `asistente/prevision.py` (LightGBM, un vector de 19 features
por entidad), el STGNN necesita una **ventana de snapshots de todo el
grafo**: `[L, N, 17]` (L horas × N nodos × 17 features), estandarizada, más
`edge_index`/`edge_weight`. Todo eso -- el orden de las features, las
medias/desviaciones de estandarización, el índice de nodos, el grafo y la
importancia de aristas precalculada -- viene en el `*.meta.json` que genera
`modelado.export.to_onnx --stgnn --meta`, vendido junto al `.onnx` (+ su
sidecar `.onnx.data`) en `asistente/modelos/`.

`target` ∈ {`calidad_aire`, `trafico`} → `stgnn_<target>.{onnx,meta.json}`.
Para `calidad_aire` un nodo es `"<station_id>__<contaminante>"`; para
`trafico` es un `point_id` de tráfico. El vector de 17 features es idéntico
para ambos (`modelado/features/panel.py` es agnóstico del target); sólo
cambia qué señal es `value` y las unidades de la salida.

El modelo predice los `n_horizontes` (1/3/6 h) de **todos** los nodos a la
vez; el llamador se queda con la fila del nodo que le interesa.

Nota honesta: los STGNN `@champion` pierden a `calidad_aire_prevista` /
`trafico_prevista` (LightGBM) en métricas puntuales con la ventana de datos
corta del proyecto (§7.4). Su valor aquí es la **trazabilidad de grafo**:
qué conexiones entre entidades pesan en la predicción.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from asistente import prevision

_MODELOS_DIR = Path(__file__).resolve().parent / "modelos"
TARGETS = ("calidad_aire", "trafico")

# 17 features del STGNN = las 19 de `prevision.FEATURES` sin `lat`/`lon`.
_IDX_17 = [i for i, f in enumerate(prevision.FEATURES) if f not in ("lat", "lon")]

_estado: "dict[str, object]" = {}


def _rutas(model_dir: Path, target: str) -> "tuple[Path, Path]":
    return model_dir / f"stgnn_{target}.onnx", model_dir / f"stgnn_{target}.meta.json"


def disponible(*, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR) -> bool:
    onnx, meta = _rutas(model_dir, target)
    return onnx.exists() and meta.exists()


def _cargar(model_dir: Path, target: str):
    if target not in TARGETS:
        raise ValueError(f"target {target!r} no soportado; usa uno de {TARGETS}")
    onnx, meta_path = _rutas(model_dir, target)
    clave = str(onnx)
    if clave not in _estado:
        import numpy as np
        import onnxruntime as ort

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        esperado = [f for f in prevision.FEATURES if f not in ("lat", "lon")]
        if list(meta["feature_cols"]) != esperado:
            raise ValueError(
                f"meta.feature_cols no casa con prevision.FEATURES sin lat/lon: {meta['feature_cols']}"
            )
        _estado[clave] = {
            "sess": ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"]),
            "meta": meta,
            "x_mu": np.asarray(meta["x_mu"], dtype="float32"),
            "x_sd": np.asarray(meta["x_sd"], dtype="float32"),
            "y_mu": np.asarray(meta["y_mu"], dtype="float32"),
            "y_sd": np.asarray(meta["y_sd"], dtype="float32"),
            "edge_index": np.asarray(meta["edge_index"], dtype="int64"),
            "edge_weight": np.asarray(meta["edge_weight"], dtype="float32"),
        }
    return _estado[clave]


def info(*, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR) -> dict:
    """`meta.json` cargado (nodos, grafo, importancia de aristas...)."""
    return dict(_cargar(model_dir, target)["meta"])


def horizontes(*, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR) -> "list[int]":
    return list(_cargar(model_dir, target)["meta"]["horizontes"])


def nodos(*, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR) -> "dict[str, int]":
    return dict(_cargar(model_dir, target)["meta"]["node_index"])


def _features_17(actual, historial, *, instante, festivos):
    v19, comp = prevision.construir_features(
        actual, historial, instante=instante, lat=0.0, lon=0.0, festivos=festivos
    )
    return [v19[i] for i in _IDX_17], comp


def predecir(
    series_por_nodo: "dict[str, dict[datetime, float]]",
    ancla: datetime,
    *,
    target: str = "calidad_aire",
    festivos: "frozenset" = frozenset(),
    model_dir: Path = _MODELOS_DIR,
) -> "tuple[dict, dict]":
    """Corre el STGNN de `target` sobre una ventana de `L` horas terminando
    en `ancla`.

    `series_por_nodo[nodo][t]` = `avg_value` de ese nodo a la hora `t`
    (`datetime`). Los nodos ausentes o sin datos entran con features a 0
    (igual que la máscara del entrenamiento).

    Devuelve `(pred_por_nodo, completeness_por_nodo)`:
    `pred_por_nodo[nodo]` = lista de `n_horizontes` valores previstos (misma
    unidad que `avg_value`); `completeness_por_nodo[nodo]` = fracción de
    features del **ancla** presentes (0..1).
    """
    import numpy as np

    st = _cargar(model_dir, target)
    meta = st["meta"]
    L = int(meta["longitud_ventana"])
    node_index = meta["node_index"]
    N, F = len(node_index), len(meta["feature_cols"])
    pasos = [ancla - timedelta(hours=L - 1 - i) for i in range(L)]

    X = np.zeros((L, N, F), dtype="float32")
    completeness: "dict[str, float]" = {}
    for nodo, idx in node_index.items():
        serie = series_por_nodo.get(nodo, {})
        for i, t in enumerate(pasos):
            actual = serie.get(t)
            historial = {k: serie.get(t - timedelta(hours=k)) for k in range(1, 25)}
            vec, comp = _features_17(actual, historial, instante=t, festivos=festivos)
            X[i, idx, :] = vec
            if t == ancla:
                completeness[nodo] = comp

    Xn = (X - st["x_mu"]) / st["x_sd"]
    y = st["sess"].run(
        None,
        {"x_seq": Xn, "edge_index": st["edge_index"], "edge_weight": st["edge_weight"]},
    )[0]  # [N, H, 1]
    y = np.asarray(y).reshape(N, -1) * st["y_sd"] + st["y_mu"]  # destandarizado

    rev = {v: k for k, v in node_index.items()}
    pred = {rev[i]: [float(x) for x in y[i]] for i in range(N)}
    return pred, completeness


def vecinos_influyentes(
    nodo: str, *, k: int = 3, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR
) -> "list[dict]":
    """De la importancia de aristas precalculada (`meta.importancia_aristas`),
    las hasta `k` conexiones más influyentes que tocan `nodo`."""
    imp = _cargar(model_dir, target)["meta"]["importancia_aristas"]
    tocan = [
        {"nodo": e["b"] if e["a"] == nodo else e["a"], "importancia": e["importancia"]}
        for e in imp
        if nodo in (e["a"], e["b"])
    ]
    return tocan[:k]
