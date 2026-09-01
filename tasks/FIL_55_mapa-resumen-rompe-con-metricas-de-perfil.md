---
kind: fil
title: "Mapa animado — el panel de resumen (FIL_49) lanza con las métricas virtuales de perfil/dosis (FIL_45), y varios controles no repintan"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-01"
resolved_at: "2026-09-01"
depends_on: [FIL_45, FIL_49]
milestone: "M4c (QA en vivo)"
source: "QA sobre el sitio publicado — https://madrono-ucm.github.io/madronoTFM/"
severity: "alta (rompe la capa social entera en el sitio público)"
---

## Contexto

QA del mapa publicado: al pulsar cualquiera de los 9 perfiles de
sensibilidad, o las métricas **salud (perfil)** / **dosis NO₂** / **dosis
O₃** (todas de `FIL_45`), el mapa se quedaba a medias y el panel inferior
dejaba de actualizarse.

## Causa raíz

`FIL_49` añadió el panel de resumen (`resumen()` + `_mediaCiudad()`) **después**
de `FIL_45`, sin contemplar las métricas virtuales de `FIL_45`, que **no
viven en `DATA[dia]`** (se calculan en el navegador):

- `_mediaCiudad(dia, "salud_perfil", h)` hacía `DATA[dia]["salud_perfil"][h]`
  → `undefined[h]` → **TypeError** propagado fuera de `render()` en cada clic
  de perfil / métrica de dosis. El panel de resumen y el pulso de distrito se
  congelaban y los siguientes clics volvían a lanzar.
- `resumen()` leía `META.metricas[m]` (undefined para las virtuales) →
  `md.peor` habría lanzado también.

Dos bugs de repintado adicionales, encontrados en la misma revisión:

- **`updateTriggers` de los nodos** (`trig`) no incluía `state.perfil` ni
  `state.escala`: con la métrica "salud (perfil)" ya activa, cambiar de
  perfil o de escala lineal↔bandas **no recoloreaba los nodos** (deck.gl
  no veía cambio en las claves).
- **`ArcLayer`**: `updateTriggers` sólo cubría `getSourceColor`, no
  `getTargetColor` → el extremo destino de los 15 arcos se quedaba con el
  color de la hora anterior.
- **`onViewStateChange`** sólo hacía `setProps({viewState})`, nunca
  `render()` → al hacer zoom/giro con el ratón no se actualizaban el radio
  de nodo (`nodeRmin`), la opacidad de las etiquetas de distrito ni el
  cambio puntos↔barras en modo "auto".

## Resolución (2026-09-01) — `viz/build_mapa_animado.py`, `_TEMPLATE`

- `_mediaCiudad()` reconoce `salud_perfil` / `dosis_no2` / `dosis_o3` y
  reutiliza `_saludPerfilHora(h)` / `_dosis(campo, guia, h)` (a `_dosis` se
  le añade el parámetro `hora`, por defecto `state.hour`).
- `resumen()` usa `metDef(m)` (que conoce `MET_EXTRA`) en vez de
  `META.metricas[m]`; la cabecera muestra un nombre legible
  ("salud (perfil X)", "dosis NO₂"…) en vez de la clave cruda.
- `trig` (updateTriggers de nodos) += `state.perfil`, `state.escala`.
- `ArcLayer`: `updateTriggers` cubre también `getTargetColor`.
- `onViewStateChange` programa un `render()` con `requestAnimationFrame`
  (un frame como mucho por gesto, sin recalcular en bucle).
- `mejorHoraPerfil()` memoizado por `(día, perfil)` — se llamaba en cada
  render (playback, pan/zoom) recorriendo 24 × 1798 nodos dos veces; ahora
  además devuelve `peor_hora` en la misma pasada (antes era un IIFE aparte
  con el mismo coste).
- Etiqueta del sub-panel "por distrito" → "salud por distrito" (siempre usa
  el índice de salud, con independencia de la métrica de color activa).

## Verificación

- Arnés headless (jsdom + stubs de deck.gl/maplibre/fetch) que dispara los
  51 controles del mapa —las 4 métricas + los 9 perfiles + escala/ghost/
  horizonte/día/representación/vista/capas/rutas/play— sobre los `*.json`
  reales: **0 excepciones** (antes: TypeError en métrica de perfil/dosis y
  en cada botón de perfil).
- `tests/test_mapa_animado.py` +1 test de regresión
  (`test_resumen_soporta_metricas_virtuales`); suite `tests/` en verde.
- `viz/mapa/index.html` regenerado (`_html()`), pendiente de republicar a
  `gh-pages` (`FIL_42`, flujo de actualización).
