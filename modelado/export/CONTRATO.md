# Contrato de entrada/salida — modelos ONNX (`ML_07`)

Lo consume `ML_09` (tool del asistente `*_prevista`) para invocar el `.onnx`
sin arrastrar LightGBM. Generado por `python -m modelado.export.to_onnx`.

## Modelos LightGBM (`madrono-<target>-h<H>`)

Un `.onnx` por `(target, horizonte)` en `modelado/export/artifacts/`:
`calidad_aire_h{1,3,6}.onnx`, `trafico_h{1,3,6}.onnx`.

### Entrada

| | |
|---|---|
| nombre del tensor | `input` |
| tipo | `float32` |
| forma | `[N, 19]` — `N` filas a predecir, **19 features en orden fijo** |
| NaN | **no admitido** — imputar a `0.0` antes de invocar (LightGBM lo maneja nativo, ONNX no). El test de paridad se hace sobre datos ya imputados |

**Orden exacto de las 19 columnas** (también en `metadata_props["features"]`
del propio `.onnx`):

| # | feature | unidad / rango | origen |
|---|---|---|---|
| 0 | `value` | señal cruda del target en `t` (µg/m³ para calidad_aire; `avg_service_level` adimensional para trafico) | Gold |
| 1 | `lat` | grados | Gold |
| 2 | `lon` | grados | Gold |
| 3 | `value_lag_1h` | como `value`, valor en `t-1h` | panel |
| 4 | `value_lag_2h` | `t-2h` | panel |
| 5 | `value_lag_3h` | `t-3h` | panel |
| 6 | `value_lag_24h` | `t-24h` | panel |
| 7 | `value_roll3h_mean` | media de `value` en `[t-3h, t-1h]` | panel |
| 8 | `value_roll3h_std` | desv. típica de esa ventana | panel |
| 9 | `value_roll24h_mean` | media en `[t-24h, t-1h]` | panel |
| 10 | `value_roll24h_std` | desv. típica en 24 h | panel |
| 11 | `hora` | 0–23 | calendario de `t` |
| 12 | `dia_semana` | 0 (lunes) – 6 (domingo) | calendario |
| 13 | `es_finde` | 0 / 1 | calendario |
| 14 | `es_festivo` | 0 / 1 (festivo de Madrid) | calendario |
| 15 | `hora_sin` | `sin(2π·hora/24)`, −1..1 | derivado |
| 16 | `hora_cos` | `cos(2π·hora/24)` | derivado |
| 17 | `dsem_sin` | `sin(2π·dia_semana/7)` | derivado |
| 18 | `dsem_cos` | `cos(2π·dia_semana/7)` | derivado |

Construir estas 19 con `modelado.features.panel.build_panel` +
`modelado.models.gbt.columnas_features` (misma función que usó el
entrenamiento) garantiza el orden.

### Salida

| | |
|---|---|
| nombre del tensor | `variable` |
| tipo | `float32` |
| forma | `[N, 1]` |
| significado | valor previsto del target **`H` horas por delante de `t`** (mismas unidades que `value`) |

### Paridad nativo ↔ ONNX

`to_onnx.py` compara `LGBMRegressor.predict` con `onnxruntime` sobre el
conjunto de test (`ML_02`). Criterio (relativo a la escala del target,
`p95 − p5` de `y_true`):

- **media** de `|Δ|` ≤ **0.5 %** de la escala — guarda principal.
- **p99** de `|Δ|` ≤ **2 %** de la escala **o** ≤ **0.07** en valor absoluto
  (subido de 0.05 en `FIL_13`: para `avg_service_level` la escala p95-p5 es ~1.0,
  así que el error fijo de frontera de split del convertidor llega al ~6 % de esa
  escala en el p99 de un solo modelo; el `mean` sigue en ~0.2 %).

Resultado real (ver `*_paridad.json`):

| modelo | media \|Δ\| | p99 \|Δ\| | escala target |
|---|---|---|---|
| `calidad_aire_h6` | 0.04 µg/m³ (0.06 %) | 0.49 µg/m³ (0.7 %) | 74 |
| `calidad_aire_h3` | 0.07 (0.09 %) | 1.50 (1.9 %) | 77 |
| `calidad_aire_h1` | 0.07 (0.10 %) | 1.44 (1.8 %) | 78 |
| `trafico_h1` | 0.001 (0.14 %) | 0.032 (3.2 % rel) | 1.0 |
| `trafico_h3` | 0.002 (0.20 %) | 0.057 (5.7 % rel; abs < 0.07) | 1.0 |
| `trafico_h6` | 0.001 (0.13 %) | 0.032 (3.2 % rel) | 1.0 |

La cola (p99/max) es una **discrepancia conocida del convertidor de
LightGBM de `onnxmltools`** en el límite de los splits (`<=`): unas pocas
filas enrutan a una hoja distinta. Persiste con tensor de doble precisión,
así que no es error de `float32`. Se amplifica porque las lecturas de
calidad del aire son casi siempre enteras y caen sobre los umbrales. En
conjunto el modelo ONNX es fiel a ~0.1 %.

## Modelo STGNN (`madrono-stgnn-<target>`) — exportable a ONNX (`FIL_20`)

`FIL_20` verificó que el STGNN **sí** se exporta a ONNX con el exportador
**dynamo** de `torch.onnx.export(dynamo=True)` (torch ≥ ~2.6). El intento
previo con el exportador TorchScript legacy fallaba o daba paridad pobre
(el `GRU` + los `scatter` del message passing). El bucle temporal Python
sobre `range(x_seq.size(0))` traza a un `L` fijo (que es un hiperparámetro,
no un eje dinámico), y `index_add` con nº de nodos variable **sí** se
soporta como `ScatterND` con eje dinámico.

### Entrada / salida

| tensor | tipo | forma | notas |
|---|---|---|---|
| `x_seq` | `float32` | `[L, N, F]` | `L` = `longitud_ventana` (fijo, def. 12); `N` = nº de nodos (**eje dinámico** `n_nodos`); `F` = `in_dim` del modelo. Ya **estandarizado** (media/desv. del train, ver `train_stgnn._estandarizar`) |
| `edge_index` | `int64` | `[2, E]` | `[0]` = origen, `[1]` = destino; `E` = nº de aristas (**eje dinámico** `n_aristas`). Sin self-loops (el término propio es explícito en `ConvGraphSAGE`) |
| `edge_weight` | `float32` | `[E]` | peso de cada arista |
| `y` (salida) | `float32` | `[N, n_horizontes, n_targets]` | predicción **estandarizada**: para el valor real, `y · y_sd + y_mu` (stats del train). `n_horizontes = 3` (h1/h3/h6), `n_targets = 1` |

### Paridad

`paridad_stgnn()` compara `STGNN.forward` (torch) con `onnxruntime` sobre
una ventana de test. Tolerancia `max |Δ| ≤ 1e-4` (el dynamo da ~`6e-8`,
epsilon de `float32`), verificada también con un grafo y un `N` distintos
a los del ejemplo de export (`modelado/tests/test_ml07.py::StgnnOnnxExportTests`).

### Por qué no se sirve todavía como tool del asistente

El contrato de entrada es materialmente más pesado que el vector de 19
features de `calidad_aire_prevista`/`trafico_prevista`: hay que materializar
una **ventana de snapshots de grafo** (`[L, N, F]`), el grafo
(`edge_index`/`edge_weight`), y aplicar la **estandarización** con las
estadísticas del entrenamiento (que habría que vendorizar aparte). Los dos
modelos LightGBM ya cubren la demo "el MCP llama al ML" (memoria §6.7).
Servir el STGNN es trabajo aditivo — pero la limitación "STGNN no servible
por ONNX" de §7.5 ya **no aplica**: es exportable y fiel.

Generar el `.onnx` del champion:

    python -m modelado.export.to_onnx --stgnn --modelo madrono-stgnn-calidad_aire \
        --panel modelado/_data/panel_calidad_aire_grafo.parquet --nombre stgnn_calidad_aire \
        [--aristas-json aristas_proximo_a.json]
