# FIL-26 — El STGNN servido como tool del MCP

`FIL_20` dejó el STGNN exportable a ONNX. Este ticket lo pone a servir como
la **10.ª tool** del asistente: `calidad_aire_prevista_grafo`. Ahora el
bucle observación→predicción→asistente se cierra también con el modelo de
grafo, y con algo que los forecasters de árboles no dan: **qué conexiones
del grafo explican la predicción**.

## Cómo se sirve un STGNN sin `torch` en runtime

El contrato de entrada del STGNN es una ventana de snapshots de grafo
`[L, N, F]` estandarizada. `modelado.export.to_onnx --stgnn --meta` genera,
junto al `.onnx` (+ sidecar `.onnx.data`), un `stgnn_calidad_aire.meta.json`:

| clave | qué |
|---|---|
| `feature_cols` | 17 — las 19 de `asistente/prevision.py::FEATURES` sin `lat`/`lon` |
| `x_mu` / `x_sd` | estandarización de entrada (del split de train) |
| `y_mu` / `y_sd` | estandarización de salida — el `.onnx` predice en z-score |
| `longitud_ventana` | 12 |
| `node_index` | 54 nodos `"<station_id>__<contaminante>"` → índice |
| `node_coords`, `edge_index`, `edge_weight` | el grafo (`coords-knn8`) |
| `importancia_aristas` | top-15 `∂pérdida/∂edge_weight` sobre el test, precalculada |

Se vendoriza en `asistente/modelos/stgnn_calidad_aire.{onnx,onnx.data,meta.json}`.

`asistente/prevision_grafo.py` carga eso (cacheado), construye `[L, 54, 17]`
reutilizando `prevision.construir_features` por nodo y por hora (recortando
`lat`/`lon`), estandariza, corre onnxruntime y destandardiza. La importancia
de aristas es **estática** (precalculada al exportar) — no se puede derivar
un gradiente desde una sesión ONNX, y para el propósito ("qué conexiones
pesan en general") una foto sobre el test es suficiente y honesta.

## La tool

`calidad_aire_prevista_grafo(zona, horizonte_horas=3, momento=None)` →
`CalidadAirePrevistaGrafo(RespuestaPrevision)`:

1. Resuelve `zona` por texto (igual que `calidad_aire_prevista`).
2. Consulta Gold para las 11 estaciones del grafo (últimas ~3 fechas).
3. Elige el par (estación, contaminante) de **peor caso** que coincide con
   `zona` (mayor ratio vs límite de referencia en el ancla).
4. Corre el STGNN sobre los **54 nodos a la vez**; devuelve la fila del nodo
   elegido para el horizonte pedido.
5. Adjunta `vecinos_influyentes` — las conexiones del grafo que más pesan en
   ese nodo (de `importancia_aristas`).

Degrada con `motivo` (sin modelo / sin estación coincidente / Athena caído /
Gold vacío) — nunca excepción. Router `GET /calidad-aire-prevista-grafo`.

## Verificación en vivo (Athena real, 2026-08-30)

| zona | nodo | actual | h1 / h3 / h6 | nivel | vecinos influyentes |
|---|---|---|---|---|---|
| Retiro | `28079049__O3` | 97 µg/m³ | 64 / 49 / 35 | buena | **Plaza del Carmen·O3 (0.010)**, Méndez Álvaro·PM10 (0.002) |
| Carmen | `28079035__O3` | 96 µg/m³ | 63 / 47 / 34 | buena | **Parque del Retiro·O3 (0.010)** |

La arista Retiro·O3 ↔ Carmen·O3 es la más influyente del grafo, y sale en
ambas direcciones — el modelo ha aprendido que esas dos estaciones de ozono
del centro se explican mutuamente.

## Honestidad (§7.4)

El STGNN `@champion` de calidad del aire **pierde a `calidad_aire_prevista`
(LightGBM) en métricas puntuales a 1 h** (skill −0.51; a 3/6 h sí bate a la
persistencia, +0.48/+0.55, `modelado/evaluation/artifacts/estudios/comparacion_todos.csv`).
La tool lo dice en su docstring y en la `explicacion` del router, y
`fiabilidad` está topada en BAJA. Se sirve **como demostración de metodología
y por la explicabilidad de grafo**, no por precisión.

## Tests

- `asistente/tests/test_calidad_aire_prevista_grafo.py` (9): previsión con
  `vecinos_influyentes`, horizonte inválido, sin estación, Athena caído,
  Gold vacío, modelo ausente, router OK / sin datos.
- `test_mcp_tools.py` / `test_mcp_transport.py` a **10 tools** (todas con
  `output_schema` + `annotations` read-only).
- Suite `asistente/` + `tests/` → 123 passed.

## Pendiente

- Sólo `calidad_aire` (único STGNN en el registry). Un STGNN de `trafico`
  seguiría el mismo patrón.
- Grafo `coords-knn8`, no las `PROXIMO_A` reales de Neo4j (reentrenar con
  `--aristas-json` = trabajo aditivo).
