---
kind: fil
title: "Mapa animado — maplibre dueño de la cámara + deck.gl como MapboxOverlay (nodos anclados, 3D real, Voyager por defecto)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
depends_on: [FIL_50]
resolved_at: "2026-09-02"
---

## Contexto — 3 bugs reportados en el sitio publicado

1. **Al cambiar de basemap, los nodos no quedan anclados** — se desplazan
   respecto a los tiles.
2. **El botón 3D no hace nada** — la cámara no se inclina, así que las
   barras extruidas (`ColumnLayer`) nunca se ven en volumen y el modo
   `auto` (barras si pitch > 5) tampoco entra.
3. El usuario quiere **Carto Voyager (calles) como basemap por defecto**.

## Causa raíz (1 y 2)

`FIL_50` montó el mapa como `new DeckGL({map: maplibregl, mapStyle})`: en
ese modo **deck.gl es dueño de la cámara** y maplibre solo la sigue. Dos
consecuencias:

- Al hacer `setProps({mapStyle})` maplibre recarga el estilo y su
  transform se desincroniza del `viewState` de deck → nodos flotando.
- `setPitch()` fijaba `state.view.pitch` y hacía `setProps({viewState})`,
  pero con un `map` provisto deck ignora los cambios de cámara vía
  `viewState` → el 3D era un no-op.

## Solución — invertir la propiedad de la cámara

Ahora **maplibre-gl es el dueño de la cámara** y deck.gl va encima como
`deck.MapboxOverlay` (control del mapa, `interleaved:false`):

- `new maplibregl.Map({style, center, zoom, pitch, bearing})` +
  `NavigationControl({visualizePitch:true})`.
- `map.addControl(new MapboxOverlay({layers:[], getTooltip}))`.
- `map.on("move")` → refresca `state.view` (lo leen `nodeRmin`, la opacidad
  de etiquetas, `usaBarras`, el aro de selección) y repinta ≤1 vez/frame.
- `render()` → `overlay.setProps({layers: layers()})` (sin `viewState`).
- `fitBounds()` → `map.fitBounds(META.bbox)`.
- `setPitch(p)` → `map.easeTo({pitch:p})` — inclinación nativa; el `move`
  resultante hace que `auto` pase a barras.
- basemap `onchange` → `map.setStyle(...)`; el `MapboxOverlay` es un
  control, sobrevive al cambio y las capas **siguen ancladas** (deck se
  renderiza dentro del bucle de maplibre, con su misma matriz de vista).

Con esto los nodos quedan anclados en cualquier basemap y a cualquier
pitch, sin la matemática de `WebMercatorViewport` (eliminada).

## Basemap por defecto

`state.basemap = "voyager"`; el `<select>` lista Voyager primero. `"ninguno"`
sigue disponible = estilo vacío transparente (deja ver el degradado del
`#map`, para capturas sin tiles / modo offline).

> **Nota**: las opacidades de las capas se afinaron para fondo oscuro
> (`FIL_48`: nodos sin dato α28, líneas de distrito α34). Sobre Voyager
> (claro) el contraste es distinto; si se quiere fondo oscuro que combine
> con los paneles, "Dark Matter" está a un clic. Un repaso de paleta para
> basemap claro sería un ticket aparte.

## Verificación

- `tests/test_mapa_animado.py` actualizado (fuera `WebMercatorViewport` /
  `HAS_MAPLIBRE` / `basemap:"ninguno"` / `bmSel.disabled`; dentro
  `new maplibregl.Map`, `MapboxOverlay`, `map.easeTo({pitch`, `voyager`
  por defecto) — 16 verde.
- `viz/test/mapa.test.mjs` (jsdom, `FIL_56`): stubs de `maplibregl.Map` /
  `MapboxOverlay`; los 51 controles → 0 excepciones. `node --check` OK.
- **Pendiente**: pasada en navegador real (estilo `VIC_32`) para confirmar
  el anclaje visual y el 3D — jsdom no tiene WebGL.

## Follow-up (2026-09-06) — cambiar de basemap fallaba

El usuario reportó que cambiar de basemap seguía roto. Tres causas, las tres corregidas:

1. **`"ninguno"` era un estilo sin ninguna capa** → maplibre deja de emitir
   `render` y el `MapboxOverlay` (enganchado a ese bucle) dejaba de dibujar
   los nodos. Ahora `"ninguno"` lleva una capa `background` oscura
   (`#0a0e14`), así que el bucle de render nunca se para.
2. **`BASEMAP_VACIO` era un objeto compartido** que `setStyle` puede mutar →
   ahora es una fábrica (`() => ({...})`) que devuelve uno nuevo cada vez.
3. **`setStyle` en modo diff** falla entre estilos muy distintos (Carto ↔
   "ninguno"). Ahora `map.setStyle(estiloBase(), {diff:false})` +
   **recrear el overlay** (`removeControl` → `setStyle` → al `styledata`
   con `isStyleLoaded`: `new MapboxOverlay(...)` + `addControl` + `render`)
   — lo más robusto frente a que el canvas del overlay se desligue.

El test funcional (`FIL_56`) ahora recorre las 4 opciones de basemap.
`tests/` 16 + `npm test` 3/3 verde.

## Follow-up (2026-09-06 b) — las barras no se veían

Causas:

1. **`radius:40, radiusUnits:"meters"`** en el `ColumnLayer` → a zoom de
   ciudad 40 m ≈ 1 px, las columnas eran invisibles (los puntos usan
   `radiusMinPixels`, las columnas no tenían nada equivalente). Ahora
   `radius:5, radiusUnits:"pixels"` → ancho fijo en pantalla.
2. **`material:{...}` sin `LightingEffect` montado** → riesgo de columnas
   negras. Ahora `material:false`: el color plano = el valor.
3. **Elegir "barras (3D)" no inclinaba la cámara** → columnas extruidas
   vistas en planta = hexágonos planos. Ahora elegir `barras` o `auto`
   con pitch < 5 hace `setPitch(45)`. `elevationScale` 24 → 35 para más
   volumen. `v3d` también pasa a 45°.

Test: `radiusUnits:"pixels"` obligatorio (no `"meters"`) + el auto-tilt.
