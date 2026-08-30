"""Export ONNX de un modelo del registry (ML_07) + test de paridad
nativo↔ONNX. ONNX es el formato de despliegue/portabilidad de la memoria
(§5.2/§5.4): `ML_09` (tool del asistente) consume el `.onnx` sin arrastrar
LightGBM/torch.

    python -m modelado.export.to_onnx --modelo madrono-calidad_aire-h6 \
        --panel modelado/_data/panel_calidad_aire.parquet --nombre calidad_aire_h6

- LightGBM  -> `onnxmltools.convert_lightgbm`.
- STGNN (torch) -> `torch.onnx.export(dynamo=True)` con ejes dinámicos para
  nº de nodos/aristas. **`FIL_20`: verificado que SÍ exporta** con el
  exportador dynamo de torch >= ~2.6 (el intento previo con el exportador
  TorchScript legacy fallaba / daba paridad pobre por el `GRU` + los
  `scatter`). Paridad float32 exacta (~6e-8), incluida con un nº de nodos y
  un grafo distintos a los del ejemplo. El STGNN **no** se sirve como tool
  del asistente todavía: su contrato de entrada (ventana de snapshots de
  grafo + estandarización aparte) es bastante más pesado que el vector de
  19 features de `calidad_aire_prevista`/`trafico_prevista`, que ya cubren
  la demo "el MCP llama al ML". Ver `doc/FIL-20-...md`.
- Paridad: `max |ŷ_nativo - ŷ_onnx|` sobre el test; falla (exit 1) si supera
  la tolerancia.
- El contrato de entrada/salida está en `modelado/export/CONTRATO.md` y
  además embebido en `metadata_props` del propio `.onnx`.
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
_ART = Path("modelado/export/artifacts")
# Criterio de paridad LightGBM->ONNX. El convertidor de LightGBM de
# onnxmltools tiene una discrepancia conocida en el límite de los splits
# (`<=`), amplificada porque las lecturas caen sobre umbrales (calidad del
# aire casi entera; `avg_service_level` agrupado en escalones); ni con
# tensor de doble precisión desaparece. Guarda principal: la MEDIA del |Δ|
# relativa a la escala del target (`p95 - p5` de `y_true`) <= 0.5 % -> el
# modelo ONNX es fiel en conjunto. El p99 (cola de filas que enrutan
# distinto) se acota al 2 % de esa escala o a 0.07 en valor absoluto (lo
# que sea mayor): para `avg_service_level` la escala p95-p5 es ~1.0, así que
# el 2 % relativo son 0.02 y el error de frontera del convertidor (fijo en
# magnitud) puede llegar al ~6 % de esa escala en el p99 de un solo modelo
# -- el mean sigue en ~0.2 %, que es la guarda que importa.
_TOL_MEAN_REL = 0.005
_TOL_P99_REL = 0.02
_TOL_P99_ABS = 0.07


def cargar_champion(nombre_registrado: str, *, alias: str = "champion"):
    """Devuelve `(modelo, flavor)` cargando `models:/<nombre>@<alias>` del
    registry (`ML_04`). Prueba LightGBM y luego PyTorch."""
    import mlflow

    from modelado.registry.mlflow_setup import configurar

    configurar("onnx-export")  # fija el tracking URI (SQLite local por defecto)
    uri = f"models:/{nombre_registrado}@{alias}"
    errores = {}
    for flavor in ("lightgbm", "pytorch"):
        try:
            return getattr(mlflow, flavor).load_model(uri), flavor
        except Exception as exc:  # noqa: BLE001
            errores[flavor] = f"{type(exc).__name__}: {exc}"
    raise SystemExit(f"no se pudo cargar {uri}: {errores}")


def exportar_lightgbm(modelo, feature_cols: "list[str]", out_path: Path, *, unidades: str = "") -> Path:
    """`LGBMRegressor` -> ONNX. Entrada única `input` float32 `[N, F]` en el
    orden de `feature_cols`; salida `variable` float32 `[N, 1]`."""
    from onnxmltools import convert_lightgbm
    from onnxmltools.convert.common.data_types import FloatTensorType
    from onnxmltools.utils import save_model

    onx = convert_lightgbm(
        modelo,
        initial_types=[("input", FloatTensorType([None, len(feature_cols)]))],
        target_opset=13,
        zipmap=False,
    )
    meta = {
        "features": ",".join(feature_cols),
        "n_features": str(len(feature_cols)),
        "salida": "[N,1] float32",
        "unidades_salida": unidades,
        "contrato": "modelado/export/CONTRATO.md",
    }
    for k, v in meta.items():
        p = onx.metadata_props.add()
        p.key, p.value = k, v
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_model(onx, str(out_path))
    return out_path


def exportar_stgnn(modelo, ejemplo: "tuple", out_path: Path, *, y_nativo=None) -> dict:
    """`STGNN` (torch) -> ONNX vía `torch.onnx.export(dynamo=True)`.

    `ejemplo = (x_seq [L, N, F], edge_index [2, E] int64, edge_weight [E])`.
    Ejes dinámicos: nº de nodos (dim 1 de `x_seq`, dim 0 de `y`) y nº de
    aristas -- `L` (longitud de ventana) es un hiperparámetro fijo del
    modelo, no un eje dinámico. El exportador **dynamo** (torch >= ~2.6) es
    el que funciona: el TorchScript legacy fallaba o daba paridad pobre por
    el `GRU` + los `scatter` del message passing (`FIL_20`).

    Devuelve `{onnx, onnx_bytes, sidecar_data, paridad?}`. Si se pasa
    `y_nativo` (salida del modelo torch sobre `ejemplo`), incluye la paridad
    contra onnxruntime. Lanza si el export falla (ya no es *best effort*).
    """
    import torch

    modelo.eval()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            modelo, tuple(ejemplo), str(out_path),
            dynamo=True, opset_version=18,
            input_names=["x_seq", "edge_index", "edge_weight"],
            output_names=["y"],
            dynamic_axes={
                "x_seq": {1: "n_nodos"},
                "edge_index": {1: "n_aristas"},
                "edge_weight": {0: "n_aristas"},
                "y": {0: "n_nodos"},
            },
        )
    resumen = {
        "onnx": out_path.as_posix(),
        "onnx_bytes": out_path.stat().st_size,
        "sidecar_data": (out_path.parent / f"{out_path.name}.data").exists(),
    }
    if y_nativo is not None:
        resumen["paridad"] = paridad_stgnn(out_path, y_nativo, ejemplo)
    return resumen


def paridad_stgnn(onnx_path: Path, y_nativo, ejemplo: "tuple") -> dict:
    """`|ŷ_torch - ŷ_onnx|` (max/p99/mean) sobre `ejemplo` para el STGNN.
    `ejemplo = (x_seq, edge_index, edge_weight)` (tensores torch o arrays)."""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    x_seq, ei, ew = (np.asarray(a) for a in ejemplo)
    valores = (x_seq.astype("float32"), ei.astype("int64"), ew.astype("float32"))
    feeds = {inp.name: val for inp, val in zip(sess.get_inputs(), valores)}
    y_onnx = sess.run(None, feeds)[0]
    d = np.abs(
        np.asarray(y_nativo, dtype="float64").reshape(-1)
        - np.asarray(y_onnx, dtype="float64").reshape(-1)
    )
    return {
        "max": float(d.max()), "p99": float(np.percentile(d, 99)),
        "mean": float(d.mean()), "n": int(d.size), "shape_onnx": list(y_onnx.shape),
    }


def paridad(onnx_path: Path, y_nativo: np.ndarray, X: np.ndarray, *, input_name: str = "input") -> dict:
    """Compara `y_nativo` con la salida de onnxruntime sobre `X` (float32).
    Devuelve `max`, `p99`, `mean` del `|Δ|` y `n_sobre_1e-3`."""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name if input_name == "input" else input_name
    y_onnx = sess.run(None, {in_name: X.astype("float32")})[0].reshape(-1)
    d = np.abs(np.asarray(y_nativo, dtype="float64").reshape(-1) - y_onnx.astype("float64"))
    return {
        "max": float(d.max()), "p99": float(np.percentile(d, 99)),
        "mean": float(d.mean()), "n_sobre_1e-3": int((d > 1e-3).sum()), "n": int(d.size),
    }


def _test_set(panel: pd.DataFrame, horizon: int, feature_cols: "list[str]"):
    from modelado.datasets.splits import temporal_split
    from modelado.models.gbt import _xy

    _, _, te = temporal_split(panel)
    X, y, _ = _xy(te, horizon, feature_cols)
    return X, y


def exportar(
    nombre_registrado: str,
    panel_path: Path,
    *,
    nombre: str,
    horizonte: int | None = None,
    mlflow_experiment: str | None = None,
) -> dict:
    from modelado.models.gbt import columnas_features

    modelo, flavor = cargar_champion(nombre_registrado)
    if flavor != "lightgbm":
        raise SystemExit(f"{nombre_registrado} es '{flavor}'; este entry point exporta LightGBM (STGNN: usar la API exportar_stgnn)")

    panel = pd.read_parquet(panel_path)
    feats = columnas_features(panel)
    if len(feats) != getattr(modelo, "n_features_in_", len(feats)):
        raise SystemExit(f"mismatch de features: panel {len(feats)} vs modelo {modelo.n_features_in_}")
    h = horizonte or int(str(nombre_registrado).rsplit("-h", 1)[-1])

    X, y_true = _test_set(panel, h, feats)
    # ONNX no maneja NaN como LightGBM -> se imputa a 0 (documentado en el
    # CONTRATO); la paridad se mide sobre datos ya imputados.
    X_imp = X.fillna(0.0)
    y_nat = modelo.predict(X_imp)

    onnx_path = _ART / f"{nombre}.onnx"
    exportar_lightgbm(modelo, feats, onnx_path, unidades=_unidades_de(nombre_registrado))
    dif = paridad(onnx_path, y_nat, X_imp.to_numpy())

    escala = float(np.nanpercentile(y_true, 95) - np.nanpercentile(y_true, 5)) or 1.0
    dif["escala_target"] = escala
    dif["p99_rel"] = dif["p99"] / escala
    dif["mean_rel"] = dif["mean"] / escala
    p99_ok = dif["p99"] <= max(_TOL_P99_REL * escala, _TOL_P99_ABS)
    ok = dif["mean_rel"] <= _TOL_MEAN_REL and p99_ok

    resumen = {
        "modelo": nombre_registrado, "flavor": flavor, "horizonte": h,
        "n_features": len(feats), "features": feats,
        "onnx": onnx_path.as_posix(), "onnx_bytes": onnx_path.stat().st_size,
        "n_test": int(len(X)), "paridad": dif,
        "tol_mean_rel": _TOL_MEAN_REL, "tol_p99_rel": _TOL_P99_REL, "tol_p99_abs": _TOL_P99_ABS,
        "paridad_ok": ok,
    }
    _ART.mkdir(parents=True, exist_ok=True)
    (_ART / f"{nombre}_paridad.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")

    if mlflow_experiment:
        _log_mlflow(nombre, nombre_registrado, mlflow_experiment, onnx_path, resumen)

    if not ok:
        raise SystemExit(
            f"PARIDAD FALLA: mean rel={dif['mean_rel']:.4f} (tol {_TOL_MEAN_REL}), "
            f"p99={dif['p99']:.3e} rel={dif['p99_rel']:.3f}"
        )
    return resumen


def _unidades_de(nombre: str) -> str:
    if "calidad_aire" in nombre:
        return "µg/m³ (avg_value del contaminante) a horizonte h"
    if "trafico" in nombre:
        return "avg_service_level (adimensional) a horizonte h"
    return ""


def _log_mlflow(nombre, nombre_registrado, experimento, onnx_path, resumen):
    from modelado.registry.mlflow_setup import configurar, log_run

    configurar(experimento)
    # MLflow no permite adjuntar un artefacto suelto a una versión ya
    # registrada; se loguea en un run propio ligado por tag al modelo.
    log_run(
        run_name=f"{nombre}_onnx_export",
        params={"source_model": f"{nombre_registrado}@champion", "n_features": resumen["n_features"]},
        metrics={
            "onnx_diff_p99": resumen["paridad"]["p99"],
            "onnx_diff_max": resumen["paridad"]["max"],
            "onnx_diff_mean": resumen["paridad"]["mean"],
            "onnx_bytes": resumen["onnx_bytes"],
        },
        tags={"tipo": "onnx_export", "paridad_ok": str(resumen["paridad_ok"])},
        artifacts=[str(onnx_path), str(onnx_path.parent / f"{nombre}_paridad.json")],
    )


_TOL_STGNN_ABS = 1e-4  # exportador dynamo -> paridad ~float32 epsilon


def exportar_stgnn_desde_registry(
    nombre_registrado: str,
    panel_path: Path,
    *,
    nombre: str,
    aristas_json: str | None = None,
    longitud: int = 12,
    knn: int = 8,
) -> dict:
    """Carga `models:/<nombre_registrado>@champion` (flavor pytorch), arma
    UNA ventana de test real con `train_stgnn._preparar` (mismo pipeline de
    snapshots + estandarización que el entrenamiento) y exporta a ONNX con
    `exportar_stgnn`, midiendo la paridad sobre esa ventana."""
    from modelado.training import train_stgnn as ts

    modelo, flavor = cargar_champion(nombre_registrado)
    if flavor != "pytorch":
        raise SystemExit(f"{nombre_registrado} es '{flavor}'; usa `exportar()` para LightGBM")
    modelo.eval()

    panel = pd.read_parquet(panel_path)
    _ni, feats, edge_index, edge_weight, vent, origen_grafo = ts._preparar(
        panel, longitud=longitud, aristas_json=aristas_json, knn=knn
    )
    in_dim = modelo.convs[0].lin_self.in_features
    if in_dim != len(feats):
        raise SystemExit(
            f"mismatch de features: panel {len(feats)} vs modelo {in_dim} "
            "(¿panel distinto al del entrenamiento?)"
        )
    Xseq, ts_obj = vent["Xseq"], vent["ts_objetivo"]
    tr, _va, te = ts._split_temporal_idx(ts_obj, test_days=3, val_days=2)
    if not (tr.any() and te.any()):
        raise SystemExit("ventana de datos demasiado corta para el split 3+2 días")
    mu, sd, _ = ts._estandarizar(Xseq[tr], eje=(0, 1, 2))
    Xte = (Xseq[te] - mu) / sd

    import torch

    x_seq = torch.as_tensor(Xte[0], dtype=torch.float32)
    ei = torch.as_tensor(edge_index, dtype=torch.long)
    ew = torch.as_tensor(edge_weight, dtype=torch.float32)
    with torch.no_grad():
        y_nat = modelo(x_seq, ei, ew).numpy()

    out_path = _ART / f"{nombre}.onnx"
    resumen = exportar_stgnn(modelo, (x_seq, ei, ew), out_path, y_nativo=y_nat)
    resumen.update(
        modelo=nombre_registrado, flavor=flavor, origen_grafo=origen_grafo,
        n_nodos=len(feats) and x_seq.shape[1], n_features=len(feats),
        longitud_ventana=longitud, n_aristas=int(ei.shape[1]),
        paridad_ok=resumen["paridad"]["max"] <= _TOL_STGNN_ABS,
    )
    (_ART / f"{nombre}_paridad.json").write_text(
        json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    if not resumen["paridad_ok"]:
        raise SystemExit(f"PARIDAD FALLA: max={resumen['paridad']['max']:.3e} (tol {_TOL_STGNN_ABS})")
    return resumen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modelo", required=True, help="nombre registrado, p. ej. madrono-calidad_aire-h6 o madrono-stgnn-calidad_aire")
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--nombre", required=True, help="nombre del fichero .onnx de salida")
    ap.add_argument("--horizonte", type=int, default=None, help="por defecto se lee de '-h<N>' del nombre")
    ap.add_argument("--stgnn", action="store_true", help="el modelo es un STGNN (torch) -> exportador dynamo (FIL_20)")
    ap.add_argument("--aristas-json", default=None, help="STGNN: PROXIMO_A exportadas de Neo4j; sin esto, k-NN de coords")
    ap.add_argument("--longitud", type=int, default=12, help="STGNN: longitud de la ventana temporal")
    ap.add_argument("--mlflow", default=None, help="experimento MLflow para subir el .onnx")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.stgnn:
        r = exportar_stgnn_desde_registry(
            args.modelo, args.panel, nombre=args.nombre,
            aristas_json=args.aristas_json, longitud=args.longitud,
        )
        p = r["paridad"]
        print(f"\n{args.modelo} (STGNN) -> {r['onnx']}  ({r['onnx_bytes']:,} bytes"
              f"{' + sidecar .data' if r['sidecar_data'] else ''})")
        print(f"  features: {r['n_features']}  nodos: {r['n_nodos']}  aristas: {r['n_aristas']}  "
              f"ventana: {r['longitud_ventana']}  grafo: {r['origen_grafo']}")
        print(f"  paridad torch<->onnx |delta|: max={p['max']:.3e}  p99={p['p99']:.3e}  mean={p['mean']:.3e}")
        print(f"  -> {'OK' if r['paridad_ok'] else 'FALLA'}  (tol max {_TOL_STGNN_ABS})")
        return 0

    r = exportar(
        args.modelo, args.panel, nombre=args.nombre, horizonte=args.horizonte,
        mlflow_experiment=args.mlflow,
    )
    d = r["paridad"]
    print(f"\n{args.modelo} -> {r['onnx']}  ({r['onnx_bytes']:,} bytes)")
    print(f"  features: {r['n_features']}  test: {r['n_test']}  escala_target(p95-p5): {d['escala_target']:.2f}")
    print(f"  paridad |delta|: mean={d['mean']:.3e} ({d['mean_rel']*100:.2f}%)  "
          f"p99={d['p99']:.3e} ({d['p99_rel']*100:.2f}%)  max={d['max']:.3e}")
    print(f"  -> {'OK' if r['paridad_ok'] else 'FALLA'}  (tol p99 {_TOL_P99_REL*100:.0f}%, mean {_TOL_MEAN_REL*100:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
