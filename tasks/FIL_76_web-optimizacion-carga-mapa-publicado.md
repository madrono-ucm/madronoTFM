---
kind: fil
title: "Web: optimizar la carga del mapa publicado (first paint, payload, CDN)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_61, FIL_69]
milestone: "M7"
---

## Motivación

Traza de rendimiento del mapa publicado (`viz/mapa/`, build de FIL_61):
**First Contentful Paint ≈ 3,0 s** — la interfaz no pinta *nada* hasta que
bajan y parsean deck.gl (~365 KB gzip) + maplibre (~210 KB gzip),
render-blocking en el `<head>`. Además `data.json` llevaba una métrica
duplicada y el basemap por defecto era el más pesado.

## Hecho

1. **Librerías del mapa fuera del `<head>`** — los `<script>` de deck.gl y
   maplibre (+ su CSS) pasan al final del `<body>`, justo antes del script
   de la app. El esqueleto (paneles, timeline, leyenda) pinta con solo el
   CSS. **FCP 3032 ms → 144 ms** (medido con Playwright/Chromium, local).
2. **`<head>` con hints de carga**:
   - `preconnect` a `cdn.jsdelivr.net`, `basemaps.cartocdn.com`,
     `tiles.basemaps.cartocdn.com` + `dns-prefetch` al host de tiles.
   - `preload as="fetch"` de `meta.json` y `data.json` → la descarga de los
     JSON grandes arranca durante el parseo del `<head>`, en paralelo con la
     librería, no después de que bootee la app.
   - `<meta name="description">`, `theme-color`, `color-scheme`.
3. **`data.json` −11 %** (2,96 MB → 2,66 MB sin comprimir; ~70 KB menos
   gzip): la clave `trafico` era **idéntica byte a byte** a `traf_h1` (misma
   columna `y_traf_h1`). Se deja de emitir; el cliente lee el modo "tráfico"
   de `traf_h1` (`_saludPerfilHora` incluido).
4. **CDN `unpkg.com` → `cdn.jsdelivr.net`** para deck.gl y maplibre —
   mismo tamaño, pero jsdelivr sirve **brotli**, tiene mejor SLA de uptime y
   está en la allowlist estándar. Versiones pineadas igual (9.0.38 / 4.7.1).
5. **Basemap por defecto Voyager → Positron** — Positron es el estilo claro
   y minimal de Carto pensado para viz de datos: fondo que no compite con
   los 1798 nodos de color, sin iconos de POI ni etiquetas de comercio.
   Mismo tile source (`carto.streets`), así que no cambia el peso de tiles,
   pero es la opción "light basemap" correcta. Conmutable como antes.

## Verificación

- `tests/test_mapa_animado.py` (16) + `viz/test/mapa.test.mjs` jsdom (3)
  verdes. Suite `viz/` + `tests/` completa verde.
- Playwright/Chromium: FCP 144 ms, sin errores de página, los 6 capítulos
  de la Historia y el panel de chat presentes, mapa renderiza 1798 nodos
  sobre Positron.
- Republicado en `gh-pages` (flujo FIL_42) — cubre también el pendiente de
  FIL_74 de subir el recorrido guiado (FIL_69) + rutas céntricas.

## No hecho (fuera de alcance / follow-up)

- Empaquetar deck.gl a medida (solo las 8 capas usadas) en vez del bundle
  `dist.min.js` completo — ahorro real pero frágil de mantener; ver FIL_75.
- `data.json` como typed-arrays base64: baja el tiempo de parse pero **sube**
  el tamaño gzip (base64 comprime peor que JSON de enteros pequeños) — mal
  canje en conexiones lentas. Descartado.
- `Cache-Control` de los JSON: fijo a 600 s en GitHub Pages, no configurable.
