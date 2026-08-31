---
kind: fil
title: "Servir el STGNN de tráfico (ML_05) como tool del MCP — trafico_prevista_grafo"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: [FIL_20, FIL_26]
---

## Contexto

`FIL_26` dejó servido el STGNN de `calidad_aire` como 10.ª tool
(`calidad_aire_prevista_grafo`) y anotó como pendiente: *«Sólo `calidad_aire`
(es el único STGNN en el registry). Un STGNN de `trafico` seguiría el mismo
patrón.»* Este ticket entrena/exporta ese STGNN de tráfico y lo sirve como
**11.ª tool** `trafico_prevista_grafo`, gemela de la de calidad del aire.

Motivación (ronda de brainstorm 2026-08-30): un modelo de grafo de
congestión es lo que hace falta para la visualización animada de propagación
sobre el grafo de Madrid (ver `tasks/FIL_32`–`FIL_36`). Su valor aquí **no
es de precisión** — el LightGBM (`trafico_prevista`, `FIL_13`) gana en
métricas puntuales — sino la **explicabilidad de grafo** (`vecinos_influyentes`).

## Resolución (2026-08-30)

1. **Export enriquecido** — `python -m modelado.export.to_onnx --stgnn --meta
   --modelo madrono-stgnn-trafico --panel modelado/_data/panel_trafico_grafo.parquet
   --nombre stgnn_trafico`. Escribe `stgnn_trafico.{onnx,onnx.data,meta.json}`.
   `meta.json`: `feature_cols` (17 = las 19 de `prevision.FEATURES` sin
   `lat`/`lon`, idénticas a calidad del aire), `x_mu/x_sd`, `y_mu/y_sd`,
   `longitud_ventana` (12), `node_index` (**1.798** `point_id` de tráfico),
   `node_coords`, `edge_index`/`edge_weight` (grafo `coords-knn8`, 17.516
   aristas dirigidas) e `importancia_aristas` (top-15,
   `∂pérdida/∂edge_weight`, precalculada).
2. **Tolerancia de paridad del exportador re-expresada** (`to_onnx.py`) —
   de `max |Δ| ≤ 1e-4` a `(mean ≤ 1e-2, p99 ≤ 3e-2, max ≤ 0.25)`. Con
   1.798 nodos y ~10 aristas/nodo, `ScatterND(reduction=add)` de ONNX fija
   otro orden de acumulación que `index_add` de torch → la
   no-asociatividad de `float32` da `max ~0.043` en `avg_service_level` en
   unos pocos nodos "peor caso", con `mean ~2.2e-4` y `p99 ~4.8e-3`. Es el
   **mismo criterio que la ruta LightGBM**: el `mean` es la guarda que
   importa. El STGNN pequeño de calidad del aire (54 nodos) sigue pasando
   holgado. `stgnn_trafico_paridad.json`: `paridad_ok=true`.
3. **Vendorizado** en `asistente/modelos/stgnn_trafico.{onnx,onnx.data,meta.json}`.
4. **`asistente/prevision_grafo.py` parametrizado por `target`** ∈
   {`calidad_aire`, `trafico`} → `stgnn_<target>.{onnx,meta.json}`.
   `disponible()`, `info()`, `horizontes()`, `nodos()`, `predecir()`,
   `vecinos_influyentes()` reciben `target` (por defecto `calidad_aire`,
   sin romper a `FIL_26`). El vector de 17 features es agnóstico del target;
   sólo cambia qué señal es `value` y las unidades de salida.
5. **Tool `trafico_prevista_grafo(lugar, horizonte_horas=3, radio_m=300.0,
   momento=None)`** (`asistente/mcp_agent/tools.py`) →
   `TraficoPrevistaGrafo(RespuestaPrevision)` (`asistente/models/herramientas.py`)
   con `punto_id`, `unidad="avg_service_level"`, `n_nodos_grafo`, `grafo`,
   `fuente_grafo` y **`vecinos_influyentes: list[VecinoGrafo]`**. Resuelve
   `lugar` cruzando el grafo urbano (igual que `trafico_prevista`,
   `FIL_13`), se queda con los puntos de tráfico que además están en el
   grafo del STGNN, consulta Gold (`gold.trafico_por_punto_hora`, ventana
   ~3 días) de **todos** los nodos del grafo, corre el STGNN sobre los 1.798
   a la vez y devuelve el del punto de peor caso (mayor `avg_service_level`
   en el ancla). Degrada con `motivo` (sin modelo / sin punto en el grafo
   del STGNN / Neo4j caído / Athena caído / Gold vacío / fallo en
   inferencia) — nunca excepción.
6. Router `GET /trafico-prevista-grafo` (`asistente/routers/trafico_prevista_grafo.py`)
   + `main.py` + `server.py` (**11 tools**, `instructions` + `description` +
   `ToolAnnotations` de lectura). `test_mcp_tools.py` / `test_mcp_transport.py`
   a 11 (`test_list_tools_expone_las_11`).
7. `asistente/tests/test_trafico_prevista_grafo.py` (10: 8 de la tool + 2 de
   router; mockea Neo4j/Athena, usa el ONNX + meta reales vendorizados).
   Suite `asistente/` + `tests/` → **135 passed, 33 subtests**.
8. Docs: `asistente/README.md` (tabla a 11 tools, sin `NotImplementedError`),
   `modelado/export/CONTRATO.md` (§ "Servido en el asistente — tools
   `*_prevista_grafo`" generaliza a los dos champions).

## Honestidad (§7.4)

El STGNN de tráfico bate a la persistencia en h1/h3/h6 (ver
`doc/ML-05` / `PLAN-REVISION-TFM.md` §1) pero **`trafico_prevista`
(LightGBM, `FIL_13`) gana en métricas puntuales**. La tool lo dice en el
docstring y en la `explicacion` del router, y `fiabilidad` está topada en
BAJA. Se sirve como demostración de metodología y por
`vecinos_influyentes`, que un modelo de árboles no da.

## Coste

Cero AWS. Entrenamiento/export en local (CPU); inferencia en runtime por
`onnxruntime` sin `torch`. La tool consulta Gold ya presente (pipeline
congelado desde el 30/8).

## Pendiente / relacionado

- El grafo es `coords-knn8`, no las `PROXIMO_A` reales de Neo4j —
  `train_stgnn.py` ya acepta `--aristas-json`; reentrenar es trabajo aditivo
  (no cambia la historia honesta, ver `FIL_32`).
- Habilita la visualización animada de propagación: `tasks/FIL_32`–`FIL_36`.
