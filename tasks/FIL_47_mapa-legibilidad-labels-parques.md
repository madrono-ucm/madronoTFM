---
kind: fil
title: "Mapa animado — legibilidad: cámara 2D/3D, etiquetas de distrito, hitos, ejes principales, parques"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_34, FIL_35]
milestone: "M4c"
target: "2026-09-12"
---

## Resolución (2026-08-31)

`viz/build_mapa_animado.py` (`_meta` + `_TEMPLATE`) reescrito:

- **Layout**: barra de título con subtítulo (día · hora · nº nodos);
  panel de control en **4 grupos `<details>` colapsables** — ⏱ Tiempo
  (día/play/slider/horizonte), 🎨 Capa de color (métricas + **leyenda
  pegada** + ghost E2 + nota de arcos), 🧭 Vista, 🚶 Ruta (E3).
- **Cámara**: botones **2D / 3D** (pitch 0 / 40) + **"encajar a Madrid"**
  (`WebMercatorViewport.fitBounds` sobre `meta.bbox`, aplicado también al
  cargar). `viewState` controlado con `onViewStateChange`.
- **Etiquetas** (capas conmutables en 🧭 Vista): `TextLayer` de nombre de
  distrito en el centroide del polígono (`meta.distrito_centroide`, 21);
  marcadores + etiqueta de los **14 hitos** de `viz/rutas.py::LUGARES`
  (incl. **Plaza Elíptica**); todos con `characterSet:"auto"` +
  `fontSettings:{sdf:true}` (acentos/ñ).
- **Ejes estructurantes**: `viz/assets/ejes_madrid.geojson` (M-30,
  Castellana, Gran Vía, A-2, A-3 — trazados **aproximados a mano**, solo
  contexto, capa off por defecto). No entran en el grafo — G9 declarado.
- **Parques**: `viz/assets/parques_madrid.geojson` (16 parques grandes,
  subconjunto curado de `parques_jardines_madrid` en Bronce) como
  puntos+etiqueta, capa off por defecto. Habilita el scoring "mejor zona
  verde" de `FIL_45` (no implementado aquí).
- **Tooltip** por nodo (`getTooltip`): id, distrito, salud/NO₂/O₃ de la
  hora; también en etiquetas de distrito, hitos y parques.
- **Ruta E3** → **dos desplegables** (origen·destino × perfil) en vez de 6
  botones + etiquetas de origen/destino sobre los extremos del trazado.
- **Accesibilidad**: `<html lang="es">`, todo el texto en español,
  `outline` de foco visible (`:focus-visible`), controles con `aria-label`,
  timeline y selectores navegables por teclado.

`viz/assets/ejes_madrid.geojson` + `viz/assets/parques_madrid.geojson`
versionados. `tests/test_mapa_animado.py` +2 (`test_meta_legibilidad`,
`test_html_legibilidad`) → `tests/` 35 en verde. JS validado con
`node --check`. `viz/mapa/` regenerado y **republicado a `gh-pages`**
(`FIL_42`).

## Objetivo

Que alguien que abre el mapa por primera vez entienda **qué está mirando**
sin tocar nada: dónde está el centro, cómo se llaman los distritos, dónde
cae Plaza Elíptica, qué es cada color.

## Alcance

### Cámara
- Toggle **2D / 3D** (pitch 0 vs el actual ~35°).
- **Auto-fit** al bounding box de los nodos al cargar y al cambiar de día
  (hoy el `initialViewState` está fijo a mano).

### Etiquetas y marcadores
- **`TextLayer` con el nombre del distrito** en su centroide (los polígonos
  ya están en `meta.json::distritos_geojson`; el centroide se calcula al
  vuelo o se precomputa en `build_mapa_animado`).
- **Marcadores de hito** para los **14 lugares** de `viz/rutas.py::LUGARES`
  (Atocha, Sol, Moncloa, …, **Plaza Elíptica** en especial — es el punto
  más contaminado y hoy no se ve).
- **Tooltip al pasar por un nodo**: id, distrito, valor de la métrica actual.
- **Etiquetas de origen/destino** de la ruta E3 + **leyenda del `ArcLayer`**
  (qué significan el color y el grosor de los arcos de importancia).
- **Barra de título** en el HTML ("Madrid — previsión sobre el grafo, día X").

### Ejes principales (contexto, sin tocar el modelo)
`PathLayer` tenue de las vías estructurantes — **M-30, A-2, A-3,
Castellana, Gran Vía** — desde un GeoJSON pequeño hecho a mano / recortado
de OSM y **versionado en `viz/assets/`**. Es **solo contexto visual**: no
entra en el grafo, no cambia el enrutado ni la previsión. Declara G9 (el
grafo sigue siendo `coords-knn8`, no la topología de calle real).

### Parques
- Capa de **`parques_jardines_madrid`** (ya ingerido; **199 parques en el
  grafo** tras `FIL_04`/`FIL_08`, aún no dibujados) — polígonos/puntos de
  los parques grandes (Retiro, Casa de Campo, Madrid Río, Juan Carlos I, …).
- Habilita un scoring **"mejor zona verde ahora / +3 h"**: para los parques
  grandes, la previsión de aire+ruido en sus nodos cercanos, ordenados —
  atado al perfil de sensibilidad de **`FIL_45`**.

### Controles
- El selector de ruta pasa a **dos desplegables** (origen·destino × perfil)
  en vez de 6 botones fijos.
- **Grupos de control colapsables** (cámara / capas / ruta / leyenda).
- La **leyenda siempre pegada a su color** (hoy está separada del selector
  de métrica).

## Qué NO hace

- **No** añade tiles de mapa base (sigue siendo distritos sobre fondo liso,
  criterio de `FIL_34`).
- **No** arregla la geometría de calle real — G9 se declara, no se resuelve.

## Coste

Cero AWS. Regenerar `viz/mapa/` + `viz/mapa_frames.png`
(`python -m viz.build_mapa_animado`).

## Verificación

Tests bajo `tests/`: el GeoJSON de ejes carga y tiene las 5 vías; los
parques del grafo se mapean a nodos; centroides de distrito dentro de su
polígono; el HTML trae `TextLayer` y los 14 hitos.

## Entregable / progreso

Milestone **M4c** en `viz/PROGRESO_MAPA.md`. Republicar a `gh-pages`
(`FIL_42`) al cerrar.
