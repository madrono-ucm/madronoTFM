---
kind: fil
title: "Grafo canónico de Madrid — artefacto exportado para viz + routing"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_31]
milestone: M1
target: "2026-09-02"
---

## Objetivo

Un único artefacto versionado del **grafo de Madrid** que usan a la vez la
visualización animada (`FIL_34`) y — si se hace — `ruta_saludable`
(`FIL_38`). Se deriva de lo que **ya usan los modelos**, sin construir un
grafo nuevo.

## Alcance

- `viz/grafo_madrid.json` (o `.parquet` + `.json`):
  - **nodos**: **1.798** `node_id` (`point_id` de tráfico) con `lat`/`lon`
    directos de `stgnn_trafico.meta.json::node_coords` (ya están, verificado
    — no hace falta otra fuente), `distrito` por point-in-polygon
    (`grafo/geo.py::point_in_geometry`, puro Python), y atributos de vía
    vacíos por ahora (los rellenaría `FIL_38` desde MTD).
  - **aristas**: `a`, `b`, `length_m` (haversine sobre `node_coords`),
    `edge_weight` de `meta.json::edge_weight`.
  - **lookup** `estación_aire → node_id` (~24) y `distrito → nodos` para
    proyectar aire (IDW) y ruido (constante por distrito) sobre el grafo.
    Ruido **no** mapea a nodo — es diario y por distrito (ver `FIL_33`).
- **Polígonos de distrito**: GeoJSON de Bronze `barrios_distritos` (lo carga
  hoy `grafo/cargar_grafo.py`) o descarga única de datos.madrid.es →
  `viz/assets/distritos_madrid.geojson` versionado. Necesario también para
  el basemap de E6.
- Fuente del grafo: `coords-knn8` del `meta.json`. Alternativa aditiva: las
  `PROXIMO_A` reales de Neo4j vía `--aristas-json` — dejar el exportador
  preparado para ambas.
- `viz/build_grafo_madrid.py` — función pura, sin credenciales.
- Tests bajo **`tests/`** (el CI recorre `... asistente/ herramientas/
  modelado/ tests/`, **no `viz/`**): nº de nodos = `len(node_index)` = 1798,
  toda arista referencia nodos válidos, todo distrito asignado o marcado.

## Coste

Cero AWS. Todo local.

## Entregable / progreso

Milestone **M1** en `viz/PROGRESO_MAPA.md`. Al cerrar: `viz/grafo_madrid.*`
en repo + primer commit de `viz/mapa_trafico_madrid.html` (sólo el grafo
estático sobre el mapa, sin animación todavía).
