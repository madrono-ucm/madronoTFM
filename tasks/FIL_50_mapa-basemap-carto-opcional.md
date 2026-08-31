---
kind: fil
title: "Mapa animado — basemap vectorial Carto opcional (opt-in, degradación elegante)"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_47]
milestone: "M4c"
target: "2026-09-13"
---

## Objetivo

Un basemap de calles/etiquetas por debajo del grafo, al estilo de lo que
pinta pydeck por defecto — **opt-in**, sin romper el principio "sin tiles,
autocontenido" de `FIL_34`.

## Alcance

- Cargar `maplibre-gl` (JS + CSS) desde CDN. `deck.DeckGL` admite
  `map: maplibregl` + `mapStyle`.
- Estilos **Carto sin token**: `positron` (claro), `dark-matter` (oscuro),
  `voyager` (calles + etiquetas, lo más parecido a "híbrido" sin satélite).
  Por defecto **"ninguno"** (estilo vacío = el aspecto actual).
- Selector "basemap" en 🧭 Vista. `setProps({mapStyle})` al cambiar.
- **Degradación elegante**: si `maplibregl` no carga (sin red / bloqueado),
  el selector se deshabilita y el mapa sigue siendo el `DeckGL` plano de
  siempre. La tira PNG y el modo offline no dependen de esto.

## Qué NO hace

- **Satélite / híbrido real** (imágenes aéreas): necesita un proveedor de
  *tiles* (Esri World Imagery, Mapbox…) con atribución/token. Se queda como
  encuadre; no encaja con "cero credenciales".

## Coste

Cero AWS. Añade 2 dependencias de CDN (solo activas si se elige un basemap).

## Verificación

Tests: el selector existe y arranca en "ninguno"; el HTML no rompe si
`maplibregl` es `undefined` (guardas). Republicar a `gh-pages` (`FIL_42`).

## Resuelto (2026-08-31) — `viz/build_mapa_animado.py`

- `<head>` carga `maplibre-gl@4.7.1` (JS + CSS) desde unpkg. Constantes
  `_MAPLIBRE_JS_CDN` / `_MAPLIBRE_CSS_CDN`, sustituidas en `_html()`.
- `DeckGL` se construye con `map: maplibregl` + `mapStyle` **solo si**
  `HAS_MAPLIBRE` (`typeof maplibregl !== "undefined"`). `state.basemap`
  arranca en `"ninguno"` → estilo vacío `{version:8,sources:{},layers:[]}`
  (transparente: se ve el degradado de siempre, cero peticiones de tiles).
- Selector `#basemap` en 🧭 Vista: ninguno · Carto Positron · Dark Matter ·
  Voyager (`basemaps.cartocdn.com/gl/*-gl-style/style.json`, sin token).
  `onchange` → `dgl.setProps({mapStyle: BASEMAPS[v]})`.
- **Degradación**: sin `maplibregl` el `<select>` queda `disabled` con
  `title` explicativo y el mapa sigue siendo el `DeckGL` plano. La tira PNG
  y el modo offline no dependen de esto.
- `tests/test_mapa_animado.py::test_html_basemap_opcional`. `tests/` → 41.
- **No** añade satélite/híbrido real (necesitaría tiles con token).
