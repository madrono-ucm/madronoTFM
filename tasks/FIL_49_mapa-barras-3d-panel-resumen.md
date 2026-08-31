---
kind: fil
title: "Mapa animado — barras extruidas (3D con sentido) + panel de resumen debajo + grafo real"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_47, FIL_48]
milestone: "M4c"
---

## Contexto

El pitch 3D no aportaba nada: los nodos eran puntos planos. Pedido:
barras en vez de puntos, un resumen visual debajo, y evaluar un basemap
tipo "híbrido" y si conviene meter gráficos con el ecosistema PyViz.

## Resolución (2026-08-31) — `viz/build_mapa_animado.py`, `_TEMPLATE`

### Barras extruidas (`ColumnLayer`)
- Nueva representación **barras**: `ColumnLayer` (disco de 6 lados, radio
  ~38 m) con `getElevation = "gravedad"` — la barra **sube donde las
  condiciones son peores** (para *salud*: `1 − t`; para NO₂/O₃/tráfico: `t`;
  en modo *ghost*: `|STGNN − persistencia|`). `getFillColor` = el mismo
  color del metric. `elevationScale` ~18 → skyline legible a pitch 40.
- Selector **representación: auto / puntos / barras** en 🧭 Vista.
  `auto` = barras cuando el pitch > 5°, puntos en 2D.
- El clic en nodo (`onClick`) y el anillo `#sel` funcionan en ambas.

### Panel de resumen debajo (`#resumen`)
Sustituye al `#ticker`. Franja inferior con 3 mini-gráficos **SVG en la
propia página** (sin dependencias nuevas):
1. **Media ciudad** de la métrica actual a lo largo de las 24 h (área +
   marcador de la hora + "ahora N · mín N @HH · máx N @HH").
2. **Por distrito** ahora: 21 barras verticales ordenadas (misma señal que
   el pulso, en formato compacto).
3. **Meteo + skill**: temperatura/viento/lluvia de la hora + skill STGNN.

### Grafo real
La capa "textura" pasa de un submuestreo 1/6 aleatorio a **todas las
aristas** del grafo (`grafo_madrid.json`, 8.758) muy tenues — "textura = el
grafo real", no un adorno. Sigue *off* por defecto.

## Descartado / futuro

- **Basemap híbrido (satélite + etiquetas)**: necesita un proveedor de
  *tiles* (Mapbox/Esri/…) → dependencia de red + token/atribución + rompe
  el principio "sin tiles, autocontenido" (G-nota de `FIL_34`). Un basemap
  vectorial **Carto** (sin token) sí es viable en Pages y queda para
  **`FIL_50`** (opt-in, con degradación elegante si no carga). Satélite real
  se queda como encuadre.
- **PyViz (HoloViews / Panel / Datashader / Bokeh)**: daría gráficos
  enlazados potentes, pero cambia el modelo de despliegue — Panel necesita
  un servidor Python (o un export Bokeh pesado), incompatible con "un HTML
  estático en `gh-pages`". Los "gráficos debajo" se hacen con SVG en la
  misma página (hecho arriba), que es autocontenido y liviano.

## Verificación

`node --check` sobre el JS; `tests/` en verde (+assert de `ColumnLayer` /
`#resumen` / selector de representación). `viz/mapa/` regenerado y
republicado a `gh-pages` (`FIL_42`).
