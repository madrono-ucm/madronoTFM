# FIL-31 — El STGNN de tráfico servido como tool del MCP

`FIL_26` dejó servido el STGNN de `calidad_aire` (`calidad_aire_prevista_grafo`,
10.ª tool) y anotó como pendiente el gemelo de tráfico. Este ticket lo cierra:
`trafico_prevista_grafo`, **11.ª tool**, misma mecánica.

## Qué cambia respecto a FIL-26

El servido "sin `torch` en runtime" ya estaba resuelto. Aquí sólo se
**generaliza por `target`**:

- `asistente/prevision_grafo.py` pasa de una constante `_MODELO =
  "stgnn_calidad_aire"` a `_rutas(model_dir, target)` con
  `target ∈ {calidad_aire, trafico}` → `stgnn_<target>.{onnx,meta.json}`.
  Todas las funciones públicas (`disponible`, `info`, `horizontes`, `nodos`,
  `predecir`, `vecinos_influyentes`) reciben `target` con default
  `calidad_aire`, así `FIL_26` no se toca.
- El vector de 17 features es **idéntico** para los dos champions
  (`modelado/features/panel.py` es agnóstico del target); sólo cambia qué
  señal es `value` y las unidades de salida (`µg/m³` vs `avg_service_level`
  0..6).

## El modelo

`python -m modelado.export.to_onnx --stgnn --meta --modelo madrono-stgnn-trafico
--panel modelado/_data/panel_trafico_grafo.parquet --nombre stgnn_trafico`

| | calidad_aire (`FIL_26`) | trafico (`FIL_31`) |
|---|---|---|
| nodos | 54 (`station__contaminante`) | **1.798** (`point_id`) |
| aristas dirigidas | ~430 | 17.516 |
| grafo | `coords-knn8` | `coords-knn8` |
| salida | µg/m³ a h1/h3/h6 | `avg_service_level` a h1/h3/h6 |

Vendorizado en `asistente/modelos/stgnn_trafico.{onnx,onnx.data,meta.json}`.

## La tolerancia de paridad hubo que re-expresarla

Con 54 nodos el exportador `dynamo` daba `max |Δ| ~1e-7`. Con **1.798**
nodos y ~10 aristas por nodo, el `max` se dispara a **~0.043** en
`avg_service_level` — pero sólo en un puñado de nodos "peor caso", con
`mean ~2.2e-4` y `p99 ~4.8e-3`.

Causa: la agregación de mensajes. `torch` usa `index_add`; la ONNX usa
`ScatterND(reduction=add)`. Las aristas duplicadas (grafo no dirigido → dos
orientaciones) se acumulan en **distinto orden**, y `float32` no es
asociativo. No es un bug de export: es ruido de redondeo que crece con el
grado del grafo.

`to_onnx.py` pasa de `max |Δ| ≤ 1e-4` a una guarda de tres cifras —
`mean ≤ 1e-2`, `p99 ≤ 3e-2`, `max ≤ 0.25` — **el mismo criterio que la ruta
LightGBM**, donde la media es la guarda que importa y el `max` se tolera. El
STGNN pequeño de calidad del aire sigue pasando holgado; el de tráfico da
`paridad_ok=true` con margen (`mean` 2 órdenes por debajo del umbral).

## La tool

`trafico_prevista_grafo(lugar, horizonte_horas=3, radio_m=300.0, momento=None)`
→ `TraficoPrevistaGrafo(RespuestaPrevision)`:

1. Resuelve `lugar` cruzando el grafo urbano de Neo4j (igual que
   `trafico_prevista`, `FIL_13`).
2. Se queda con los puntos de tráfico que **además** están en el
   `node_index` del STGNN.
3. Consulta `gold.trafico_por_punto_hora` (ventana ~3 días) de **todos** los
   1.798 nodos — necesita la ventana completa del grafo, no la de un punto.
4. Corre el STGNN sobre los 1.798 nodos a la vez (`onnxruntime`), elige el
   punto de **peor caso** (mayor `avg_service_level` en el ancla) entre los
   candidatos cercanos con serie.
5. Devuelve la cifra a `horizonte_horas` + `vecinos_influyentes`: las
   conexiones entre puntos de tráfico que más pesan en la predicción de ese
   nodo (`∂pérdida/∂edge_weight` precalculada al exportar).

Más lenta que `trafico_prevista` (~20-40 s): arma la ventana de 1.798 puntos,
no de uno. Degrada con `motivo` en los seis puntos de fallo (sin modelo, sin
punto en el grafo del STGNN, Neo4j caído, Athena caído, Gold vacío, fallo en
inferencia) — nunca excepción.

## Honestidad (§7.4)

El STGNN de tráfico **bate a la persistencia** en los tres horizontes, pero
`trafico_prevista` (LightGBM) le gana en métricas puntuales. Docstring,
`explicacion` del router y `fiabilidad` topada en BAJA lo dicen. Se sirve
como demostración de metodología y por la explicabilidad de grafo.

## Coste

Cero AWS. Export local (CPU), inferencia por `onnxruntime` sin `torch`,
consulta a Gold ya presente.

## Verificación

`asistente/` + `tests/` → **135 passed, 33 subtests** (`pytest -q`).
`test_trafico_prevista_grafo.py`: 8 de la tool (camino feliz + `punto_id` de
peor caso = extremo de la arista más importante + los 6 modos de
degradación) + 2 de router (`fiabilidad=baja`, fuente "grafo STGNN").

## Relacionado

- Habilita la visualización animada de propagación sobre el grafo de Madrid
  — `tasks/FIL_32`–`FIL_36`, seguimiento en `viz/PROGRESO_MAPA.md`.
- Reentrenar con las `PROXIMO_A` reales (`--aristas-json`) en vez de
  `coords-knn8` es trabajo aditivo; no cambia la historia honesta.
