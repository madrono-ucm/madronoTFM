# FIL-20 — Ruta de serving para el STGNN

Ticket opcional (`doc/PLAN-REVISION-TFM.md`, "sólo si sobra tiempo"):
*investigar una ruta de serving para el STGNN*. La memoria lo daba por
imposible ("STGNN no servible por ONNX", §7.5).

## Resultado: SÍ es exportable a ONNX

Probadas las rutas de export con `torch 2.13.0+cpu` (`modelado/models/stgnn.py`,
GraphSAGE+GRU hecho a mano):

| Ruta | Resultado |
|---|---|
| `torch.onnx.export(dynamo=True)` (opset 18) | ✅ **funciona**. Paridad `max |Δ| ≈ 6e-8` (epsilon de `float32`), sobre el propio ejemplo **y** sobre un grafo con distinto nº de nodos/aristas. El nº de nodos y de aristas quedan como **ejes dinámicos** reales (`index_add` → `ScatterND`). |
| `torch.onnx.export(dynamo=False)` (TorchScript legacy, opset 17) | Exporta un `.onnx` pero **paridad pobre** (`max |Δ| ≈ 0.12`) — el `GRU` y/o los `scatter` del message passing se traducen mal. Era la ruta que probaba el código antiguo de `exportar_stgnn`. |
| `torch.jit.script` / `torch.jit.trace` | Ambas OK — sirven para LibTorch/TorchScript, pero mantienen la dependencia de `torch` en runtime, que es justo lo que ONNX evita. |

La afirmación de que "`torch.export` no traza el `forward`" era cierta con
versiones antiguas de torch; el exportador **dynamo** (estable desde
~torch 2.6) sí lo hace: el bucle temporal Python sobre `range(x_seq.size(0))`
traza a un `L` fijo (que es un hiperparámetro, no un eje dinámico) y el
message passing con `index_add` se soporta con nº de nodos variable.

## Qué se implementó

- **`modelado/export/to_onnx.py`**:
  - `exportar_stgnn(modelo, ejemplo, out_path, *, y_nativo=None)` reescrita:
    `dynamo=True`, ejes dinámicos nodos/aristas, ya **no** es *best effort*
    (lanza si falla), devuelve `{onnx, onnx_bytes, sidecar_data, paridad?}`.
  - `paridad_stgnn(onnx_path, y_nativo, ejemplo)` — `max/p99/mean |Δ|` para la
    firma multi-input del STGNN.
  - `exportar_stgnn_desde_registry(nombre, panel_path, *, aristas_json, longitud)`
    + `--stgnn` en el CLI: carga `models:/madrono-stgnn-<target>@champion`,
    arma una ventana de test real con `train_stgnn._preparar` (mismos
    snapshots + estandarización que el entrenamiento) y exporta con paridad
    (`tol max 1e-4`).
- **`modelado/tests/test_ml07.py::StgnnOnnxExportTests`**: export sintético
  + paridad exacta + nº de nodos dinámico. `skipUnless(torch)`.
- **`modelado/export/CONTRATO.md`**: sección STGNN reescrita con el
  contrato de entrada/salida (`x_seq [L,N,F]` estandarizado, `edge_index`,
  `edge_weight` → `y [N,3,1]` estandarizado) y la tolerancia de paridad.

## Por qué NO se sirve como tool del asistente (todavía)

Decisión deliberada, no un bloqueo técnico:

- El contrato de entrada es mucho más pesado que el vector de 19 features de
  `calidad_aire_prevista`/`trafico_prevista`: hay que materializar una
  **ventana de snapshots de grafo** `[L, N, F]`, el grafo
  (`edge_index`/`edge_weight`) y aplicar la **estandarización** con las
  estadísticas del entrenamiento (a vendorizar aparte, junto al `.onnx` +
  su sidecar `.data`).
- Los dos modelos LightGBM ya cubren la demostración "el MCP llama al ML"
  de la memoria §6.7, con dos targets distintos.
- El STGNN se presenta como **resultado de §7.2** (bate a persistencia en
  `trafico` en todos los horizontes) — servirlo es valor añadido, no
  requisito de la demo.

## Efecto en la memoria

`§7.5` / `VIKT_07`: la limitación **"STGNN no servible por ONNX" ya no
aplica** — el modelo es exportable y fiel (`max |Δ| ~ 6e-8`). La redacción
correcta es: *el STGNN es exportable a ONNX (dynamo); no se ha integrado
como tool del asistente porque su contrato de entrada
(ventana de grafo + estandarización) es más pesado que el de los
forecasters LightGBM, que ya cubren la demo — queda como trabajo aditivo.*
Pregunta de defensa "¿por qué el STGNN no se sirve?" (`VIKT_10`) → esta
respuesta.
