---
kind: fil
title: "Mapa animado del grafo de Madrid — HTML (pydeck), núcleo"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_33]
milestone: M3
target: "2026-09-08"
---

## Objetivo

El elemento "wow" del TFM: el grafo de 1.798 nodos sobre Madrid, latiendo
con la previsión hora a hora, con las aristas influyentes destacadas.

## Alcance — núcleo (E1 / E5 / E7)

- `viz/build_mapa_animado.py` → `viz/mapa_trafico_madrid.html` (pydeck /
  deck.gl, basemap Carto Positron sin token). Mismo script emite
  `viz/mapa_frames.png` (tira de 6 fotogramas, **districtos GeoJSON de
  fondo, sin tiles web** — determinista, para la memoria).
- **Datos**: `prevision_animada.parquet` → JSON. **1.798 nodos × 24 h ×
  2-3 días ≈ 10-25 MB** → se sirve como **fichero externo cargado en
  runtime** (`fetch` relativo, OK en Pages), no todo inline. Redondear a
  1 decimal. Si aún pesa: 1-2 días, o adelgazar a los ~600 nodos con más
  varianza.
- **Héroe**: el grafo. `ScatterplotLayer` (nodos, radio+color por métrica),
  `LineLayer` (aristas, ancho/color por tráfico previsto).
- **E1 — aristas influyentes**: el `ArcLayer` dibuja el **conjunto fijo
  top-15** de `importancia_aristas` (es estático, precalculado — no hay
  importancia por hora). Se anima su opacidad/altura con el tráfico previsto
  en los extremos: "estos corredores mandan, y ahora mismo van así".
- **E5**: bucle de 24 h, día curado + selector (2-3 días data-driven),
  play/pause/scrub, lectura de hora + **ticker meteo desde
  `gold.meteorologia_*` (Ayuntamiento, datos.madrid.es — 15 días,
  exportado en `FIL_33`)**, sólo para los días curados. Toggle de horizonte
  now / +1h / +3h / +6h.
- **E7**: selector de métrica del color de nodo — tráfico previsto | NO₂ |
  O₃ | **índice de salud 0-100** (por defecto). Ruido **no** es selector
  animado (es constante diario por distrito, ver `FIL_33`); aparece como
  capa de contexto opcional. Leyenda "bueno para pedalear / estar ahora".
- Sin interacción de ruta todavía (E3 llega en `FIL_37`).

## Dependencias nuevas

`viz/requirements.txt`: `pydeck`, `pandas`, `pyarrow`, `matplotlib`. Sin
`shapely`/`geopandas` — el point-in-polygon es `grafo/geo.py` (puro Python).

## Consecuencia asumida del stack

pydeck necesita red al visualizar (bundle deck.gl + tiles del basemap) → se
sirve como **URL en GitHub Pages**, no como artefacto de claude.ai ni 100 %
offline. Defensa: wifi de sala, o vendorizar el bundle + `python -m
http.server`. La tira PNG es el respaldo offline y la figura de la memoria.

## Coste

Cero AWS.

## Entregable / progreso

Milestone **M3** en `viz/PROGRESO_MAPA.md` — primer HTML **animado**. A
partir de aquí cada milestone re-publica el mismo fichero, así el entregable
se ve crecer.
