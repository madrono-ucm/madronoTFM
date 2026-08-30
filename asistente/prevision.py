"""Previsión desde los modelos ONNX de `ML_07` (tools `calidad_aire_prevista`
y `trafico_prevista`).

Cierra el bucle de la memoria §6.7 / §4.1: observación → predicción →
asistente. Los `.onnx` los produce `modelado.export.to_onnx` a partir de
`madrono-<target>-h<H>@champion` del registry (`ML_04`); aquí se sirven
copias vendidas en `asistente/modelos/` (`<target>_h<H>.onnx`).

`target` ∈ {`calidad_aire`, `trafico`}. El **vector de features es idéntico**
para ambos (`modelado/features/panel.py` es agnóstico del target): lags y
rolling del propio target + calendario. Sólo cambia qué señal es `value`
(`avg_value` del contaminante vs `avg_service_level` del punto) y las
unidades de la salida.

Contrato de entrada = `modelado/export/CONTRATO.md`: tensor `input` float32
`[N, 19]` con las 19 features en orden fijo; **NaN no admitido → se imputa a
0.0** (igual que en el test de paridad de `ML_07`). Salida `[N, 1]`: valor
previsto del target `H` horas por delante.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

_MODELOS_DIR = Path(__file__).resolve().parent / "modelos"
_HORIZONTES = (1, 3, 6)
TARGETS = ("calidad_aire", "trafico")

# Orden EXACTO de CONTRATO.md. No reordenar.
FEATURES = (
    "value", "lat", "lon",
    "value_lag_1h", "value_lag_2h", "value_lag_3h", "value_lag_24h",
    "value_roll3h_mean", "value_roll3h_std",
    "value_roll24h_mean", "value_roll24h_std",
    "hora", "dia_semana", "es_finde", "es_festivo",
    "hora_sin", "hora_cos", "dsem_sin", "dsem_cos",
)
_LAGS_CLAVE = (1, 2, 3, 24)  # las que cuentan para data_completeness

_sesiones: "dict[Path, object]" = {}


def _media(xs: "list[float]") -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _desv(xs: "list[float]") -> float:
    # desviación típica muestral (ddof=1), como el rolling().std() de pandas;
    # con <2 observaciones pandas da NaN -> aquí 0.0 (se imputa igual que en
    # el entrenamiento servido a ONNX).
    if len(xs) < 2:
        return 0.0
    m = _media(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def construir_features(
    actual: "float | None",
    historial: "dict[int, float]",
    *,
    instante: datetime,
    lat: "float | None",
    lon: "float | None",
    festivos: "frozenset" = frozenset(),
) -> "tuple[list[float], float]":
    """Construye el vector de 19 features + `data_completeness`.

    `historial[k]` = `avg_value` de hace `k` horas (`k` en 1..24); las que
    falten se imputan a 0.0. `data_completeness` = fracción de {valor actual,
    lag 1h, 2h, 3h, 24h} realmente presente (mismo criterio de "fiabilidad
    baja si faltan features" que `afluencia_estimada`).
    """
    v = float(actual) if actual is not None else 0.0
    lag = {k: historial.get(k) for k in _LAGS_CLAVE}

    v3 = [historial[k] for k in (1, 2, 3) if historial.get(k) is not None]
    v24 = [historial[k] for k in range(1, 25) if historial.get(k) is not None]

    hora = instante.hour
    dow = instante.weekday()  # lunes=0
    valores = {
        "value": v,
        "lat": float(lat) if lat is not None else 0.0,
        "lon": float(lon) if lon is not None else 0.0,
        "value_lag_1h": lag[1] or 0.0,
        "value_lag_2h": lag[2] or 0.0,
        "value_lag_3h": lag[3] or 0.0,
        "value_lag_24h": lag[24] or 0.0,
        "value_roll3h_mean": _media(v3),
        "value_roll3h_std": _desv(v3),
        "value_roll24h_mean": _media(v24),
        "value_roll24h_std": _desv(v24),
        "hora": float(hora),
        "dia_semana": float(dow),
        "es_finde": 1.0 if dow >= 5 else 0.0,
        "es_festivo": 1.0 if instante.date() in festivos else 0.0,
        "hora_sin": math.sin(2 * math.pi * hora / 24),
        "hora_cos": math.cos(2 * math.pi * hora / 24),
        "dsem_sin": math.sin(2 * math.pi * dow / 7),
        "dsem_cos": math.cos(2 * math.pi * dow / 7),
    }
    vector = [float(valores[f]) for f in FEATURES]
    presentes = sum(1 for x in (actual, lag[1], lag[2], lag[3], lag[24]) if x is not None)
    return vector, presentes / (len(_LAGS_CLAVE) + 1)


def _sesion(path: Path):
    import onnxruntime as ort

    if path not in _sesiones:
        _sesiones[path] = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return _sesiones[path]


def modelo_disponible(
    horizonte: int, *, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR
) -> bool:
    return (model_dir / f"{target}_h{horizonte}.onnx").exists()


def predecir(
    vector: "list[float]", *, horizonte: int, target: str = "calidad_aire", model_dir: Path = _MODELOS_DIR
) -> float:
    """Corre el `.onnx` de `<target>_h<horizonte>` sobre un vector de 19 features."""
    if horizonte not in _HORIZONTES:
        raise ValueError(f"horizonte {horizonte} no soportado; usa uno de {_HORIZONTES}")
    if target not in TARGETS:
        raise ValueError(f"target {target!r} no soportado; usa uno de {TARGETS}")
    path = model_dir / f"{target}_h{horizonte}.onnx"
    if not path.exists():
        raise FileNotFoundError(f"no está el modelo ONNX {path} (genéralo con modelado.export.to_onnx)")
    import numpy as np

    sess = _sesion(path)
    x = np.asarray([vector], dtype="float32")
    salida = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    return float(np.asarray(salida).ravel()[0])
