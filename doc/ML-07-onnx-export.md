# ML-07 — Export ONNX del modelo registrado + paridad + contrato

## Qué se creó

- **`modelado/export/to_onnx.py`**
  - `cargar_champion(nombre)` — carga `models:/<nombre>@champion` del
    registry (`ML_04`); prueba flavor `lightgbm` y luego `pytorch`.
  - `exportar_lightgbm(modelo, feature_cols, out)` — `onnxmltools.
    convert_lightgbm`, entrada única `input` float32 `[N, F]` en el orden
    de `feature_cols`, salida `variable` float32 `[N, 1]`. Embebe la lista
    de features + unidades + puntero al contrato en `metadata_props`.
  - `exportar_stgnn(modelo, ejemplo, out)` — `torch.onnx.export` con
    `dynamic_axes` sobre nº de nodos/aristas. **Best effort** (ver abajo).
  - `paridad(onnx, y_nativo, X)` — corre `onnxruntime` y devuelve
    `mean / p99 / max` de `|Δ|` + `n_sobre_1e-3`.
  - `exportar(...)` — orquesta: champion → panel → test set (`ML_02`) →
    export → paridad → `modelado/export/artifacts/<nombre>.onnx` +
    `<nombre>_paridad.json`; sube el `.onnx` a MLflow si `--mlflow`.
- **`modelado/export/CONTRATO.md`** — nombres, orden, tipos y unidades de
  las 19 features de entrada, forma de la salida (`[N, 1]`, valor a `H` h),
  manejo de NaN (imputar a 0), y el criterio + resultado de paridad.
- **`modelado/tests/test_ml07.py`** — 3 tests autocontenidos (LightGBM tiny
  sintético): I/O y `metadata_props` del `.onnx`, paridad nativo↔ONNX
  (media diminuta con datos gaussianos), forma del `dict` de paridad.

`onnx 1.22` / `onnxruntime 1.29` / `onnxmltools 1.16` / `onnxscript 0.7`
(wheels binarios, Python 3.14). Añadidos a `modelado/requirements.txt`.
`python -m pytest modelado/ -q` → **35 passed**.

## Modelos exportados (reales, desde el registry)

`python -m modelado.export.to_onnx --modelo madrono-<t>-h<H> --panel … --nombre <t>_h<H> --mlflow tier1`

| `.onnx` | bytes | media \|Δ\| | p99 \|Δ\| | escala target (p95−p5) | paridad |
|---|---|---|---|---|---|
| `calidad_aire_h6` | 87 914 | 0.042 µg/m³ (0.06 %) | 0.49 (0.7 %) | 74 | ✅ |
| `calidad_aire_h3` | 136 954 | 0.071 (0.09 %) | 1.50 (1.9 %) | 77 | ✅ |
| `calidad_aire_h1` | 801 569 | 0.075 (0.10 %) | 1.44 (1.8 %) | 78 | ✅ |
| `trafico_h6` | 1 358 605 | 0.0013 (0.13 %) | 0.032 (3.2 % rel; < 0.05 abs) | 1.0 | ✅ |

### Tolerancia — y por qué

Criterio (relativo a la escala del target):

- **media** de `|Δ|` ≤ **0.5 %** — guarda principal (fidelidad de conjunto).
- **p99** de `|Δ|` ≤ **2 %** de la escala **o** ≤ **0.05** absoluto (para
  targets de rango comprimido como `avg_service_level`).

La cola (`p99`/`max`) es una **discrepancia conocida del convertidor de
LightGBM de `onnxmltools`** en el límite de los splits (`x <= umbral`): unas
pocas filas caen sobre el umbral y enrutan a una hoja distinta. **Persiste
con tensor de doble precisión** → no es error de `float32`. Se amplifica
porque las lecturas de calidad del aire son casi siempre enteras y coinciden
con los umbrales. En conjunto el ONNX reproduce LightGBM a ~0.1 % (mean),
muy por debajo del error propio del modelo (RMSE ~8 µg/m³ en calidad_aire).

## MLflow

MLflow 3 no deja adjuntar un artefacto suelto a una versión ya registrada,
así que cada export se loguea como un **run propio** (`<nombre>_onnx_export`
en el experimento del modelo) con el `.onnx` + el `paridad.json` como
artefactos y `source_model` en los params. `ML_09` carga el `.onnx` desde
`modelado/export/artifacts/` (o desde ese run).

## STGNN → ONNX: pendiente (documentado)

`exportar_stgnn()` está implementada pero `torch.export` (única ruta de
`torch.onnx.export` en torch 2.13) **no traza el `forward` del STGNN**:
bucle temporal en Python sobre la ventana + `index_add` con nº de nodos
dependiente de los datos (`RuntimeError: a and b must have same reduction
dim`). Mientras tanto el STGNN se sirve desde su entrada PyTorch del
registry (`models:/madrono-stgnn-<target>@champion`). Export ONNX del GNN =
línea futura (§7.5): refactor a un `forward` de forma fija / vectorizado, o
esperar más cobertura de `torch.export`.

## Criterios de aceptación

- [x] `.onnx` generado para el mejor modelo de calidad del aire
  (`calidad_aire_h6`) — y además h1/h3 y `trafico_h6`.
- [x] Test de paridad en verde, con la tolerancia anotada (arriba y en
  `CONTRATO.md`).
- [x] `CONTRATO.md` completo (19 features, orden, unidades, salida, NaN).
- [x] `.onnx` subido como artefacto en MLflow.
- [x] `onnx`/`onnxruntime`/`onnxmltools` en `modelado/requirements.txt`.
- [~] GNN → ONNX: intentado, bloqueado por `torch.export`; documentado.

## Pendiente / lo retoman otros tickets

- `ML_09` — la tool del asistente `*_prevista` carga estos `.onnx` con
  `onnxruntime` y construye las 19 features vía `modelado.features.panel`.
- STGNN → ONNX cuando el `forward` se refactorice o `torch.export` avance.
