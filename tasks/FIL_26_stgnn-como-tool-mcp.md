---
kind: fil
title: "Servir el STGNN (ML_05) como tool del MCP — calidad_aire_prevista_grafo"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: [FIL_20]
---

## Contexto

`FIL_20` verificó que el STGNN es exportable a ONNX (`dynamo`, paridad
~1e-7). Este ticket lo **sirve** como 10.ª tool del asistente, cerrando el
bucle también para el modelo de grafo.

## Resolución (2026-08-30)

1. **Export enriquecido** — `modelado.export.to_onnx --stgnn --meta` escribe,
   junto al `.onnx` (+ sidecar `.onnx.data`), un `stgnn_calidad_aire.meta.json`
   con todo lo que hace falta para servirlo **sin torch**: `feature_cols`
   (17 = las 19 de `prevision.FEATURES` sin `lat`/`lon`), `x_mu/x_sd`,
   `y_mu/y_sd`, `longitud_ventana` (12), `node_index` (54 nodos
   `"<station_id>__<contaminante>"`), `node_coords`, `edge_index`/`edge_weight`
   (grafo `coords-knn8`) e `importancia_aristas` (top-15,
   `∂pérdida/∂edge_weight` sobre el test, precalculada).
2. **Vendorizado** en `asistente/modelos/stgnn_calidad_aire.{onnx,onnx.data,meta.json}`.
3. **`asistente/prevision_grafo.py`** — carga ONNX + meta (cacheado),
   construye la ventana `[L, N, 17]` estandarizada a partir de una serie
   `avg_value` por nodo, corre onnxruntime, destandardiza. `vecinos_influyentes(nodo)`
   lee la importancia de aristas precalculada.
4. **Tool `calidad_aire_prevista_grafo(zona, horizonte_horas=3, momento=None)`**
   (`asistente/mcp_agent/tools.py`) → `CalidadAirePrevistaGrafo(RespuestaPrevision)`
   con `nodo`, `n_nodos_grafo`, `grafo` y **`vecinos_influyentes`** (lista de
   `VecinoGrafo`). Resuelve `zona` por texto igual que `calidad_aire_prevista`,
   consulta Gold para las 11 estaciones del grafo, elige el par
   (estación, contaminante) de peor caso, corre el STGNN sobre los 54 nodos y
   devuelve la fila del nodo elegido. Degrada con `motivo` (sin modelo, sin
   estación, Athena caído, Gold vacío) — nunca excepción.
5. Router `GET /calidad-aire-prevista-grafo` + `main.py` + `server.py`
   (**10 tools**) + `test_mcp_tools.py` / `test_mcp_transport.py` a 10.
6. `asistente/tests/test_calidad_aire_prevista_grafo.py` (9). Suite
   `asistente/` + `tests/` → 123 passed.
7. **Verificado en vivo** contra Athena real (2026-08-30):
   - «Retiro» → nodo `28079049__O3`, actual 97 µg/m³ → h1=64, h3=49, h6=35 «buena»;
     vecinos influyentes: **Plaza del Carmen·O3 (0.010)**, Méndez Álvaro·PM10 (0.002).
   - «Carmen» → `28079035__O3`, vecino influyente **Parque del Retiro·O3 (0.010)**
     (simétrico — es la arista más importante del grafo).

## Honestidad (§7.4)

El STGNN `@champion` **pierde a `calidad_aire_prevista` (LightGBM) en
métricas puntuales a 1 h** (skill −0.51; sí bate a la persistencia a 3/6 h,
+0.48/+0.55). La tool lo dice en el docstring y en la `explicacion` del
router, y la `fiabilidad` está topada en BAJA. Se sirve como demostración de
metodología y por la **explicabilidad de grafo** (`vecinos_influyentes`),
que un modelo de árboles no da.

## Pendiente / relacionado

- Sólo `calidad_aire` (es el único STGNN en el registry). Un STGNN de
  `trafico` seguiría el mismo patrón.
- El grafo es `coords-knn8`, no las `PROXIMO_A` reales de Neo4j — reentrenar
  con `--aristas-json` es trabajo aditivo.
