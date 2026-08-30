---
kind: fil
title: "El grafo como eje de la memoria — figura, DATA_SOURCES, promoción de ítems de encuadre"
owner: Filippos (interactive) + coordinación VIKT
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_35]
milestone: M5
---

## Objetivo

Cerrar el círculo en la memoria: el TFM se lee como "un análisis sobre el
grafo de Madrid", con el mapa animado como artefacto tangible.

## Alcance (parte editorial se coordina con VIKT_10)

- **Figura de la memoria**: la tira `viz/mapa_frames.png` + subsección
  "Visualización animada de la previsión sobre el grafo" (alimenta `VIKT_06`
  / demo de defensa).
- **`DATA_SOURCES.md`** en la raíz: atribución CC BY 4.0 de las fuentes
  externas usadas o citadas — MTD (Gómez & Ilarri, `10.17632/697ht4f65b.4`),
  meteo histórica de la Comunidad de Madrid — además de las municipales ya
  documentadas.
- **Promoción de ítems de encuadre** (decidido 2026-08-30):
  - **city-planner inputs** → *entregado*: la vista agregada de importancia
    de aristas es un artefacto de planificación; se describe como demostrado,
    no como trabajo futuro.
  - **hosted endpoint** → *entregado parcial*: el mapa está en una URL
    (Pages). Una API de predicción de producción sigue siendo trabajo futuro.
  - **open dataset** y **cyclist / movilidad reducida routing** → siguen
    siendo encuadre; se refuerza el texto ("el sustrato de datos ya existe")
    sin comprometer entregable.
- Reestructura ligera del índice de la memoria hacia el eje del grafo
  (construcción → señales → previsión → recomendación → servido → resultados).

## Coste

Cero AWS.

## Entregable / progreso

Milestone **M5** en `viz/PROGRESO_MAPA.md`.
