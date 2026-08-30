---
kind: fil
title: "Grafo canónico de Madrid — artefacto exportado para viz + routing"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_31]
milestone: M1
---

## Objetivo

Un único artefacto versionado del **grafo de Madrid** que usan a la vez la
visualización animada (`FIL_34`) y — si se hace — `ruta_saludable`
(`FIL_38`). Se deriva de lo que **ya usan los modelos**, sin construir un
grafo nuevo.

## Alcance

- `viz/grafo_madrid.json` (o `.parquet` + `.json`):
  - **nodos**: `node_id`, `lat`, `lon`, `distrito` (join contra
    `barrios_distritos_madrid`), y atributos de vía cuando existan
    (`road_class`, `lanes`, `oneway`, `length_m`) — de MTD si se incorpora
    en `FIL_39`, si no vacíos.
  - **aristas**: `a`, `b`, `length_m` (haversine si no hay geometría),
    `edge_weight` (el del `meta.json` del STGNN de tráfico).
  - **lookup** `sensor_estacion → node_id`: cada estación de calidad del
    aire y cada sonómetro de ruido a su nodo de tráfico más cercano
    (haversine), para proyectar sus señales sobre el grafo.
- Fuente del grafo: `coords-knn8` del `stgnn_trafico.meta.json`
  (`edge_index`/`edge_weight`/`node_coords`). Alternativa aditiva: las
  `PROXIMO_A` reales de Neo4j vía `--aristas-json` — dejar el exportador
  preparado para ambas.
- `viz/build_grafo_madrid.py` — función pura, sin credenciales (lee el
  `meta.json` vendorizado + un dump de polígonos de distrito ya en repo o
  descargable una vez).
- Tests: `viz/tests/test_grafo_madrid.py` — nº de nodos = `len(node_index)`,
  toda arista referencia nodos válidos, todo sensor mapea a un nodo.

## Coste

Cero AWS. Todo local.

## Entregable / progreso

Milestone **M1** en `viz/PROGRESO_MAPA.md`. Al cerrar: `viz/grafo_madrid.*`
en repo + primer commit de `viz/mapa_trafico_madrid.html` (sólo el grafo
estático sobre el mapa, sin animación todavía).
