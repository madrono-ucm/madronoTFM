---
kind: fil
title: "Mapa animado — basemap vectorial Carto opcional (opt-in, degradación elegante)"
owner: Filippos (interactive)
status: pending
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
