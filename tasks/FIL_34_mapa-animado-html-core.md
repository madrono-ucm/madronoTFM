---
kind: fil
title: "Mapa animado del grafo de Madrid — HTML (pydeck), núcleo"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_33]
milestone: M3
---

## Objetivo

El elemento "wow" del TFM: el grafo de 1.798 nodos sobre Madrid, latiendo
con la previsión hora a hora, con las aristas más influyentes iluminándose
antes de que el nodo aguas abajo reaccione.

## Alcance — núcleo (E1 / E5 / E7)

- `viz/build_mapa_animado.py` → `viz/mapa_trafico_madrid.html` **autónomo**
  (pydeck / deck.gl, basemap Carto Positron sin token). Mismo script emite
  `viz/mapa_frames.png` (tira de 6 fotogramas, sin tiles, para la memoria).
- **Héroe**: el grafo. `ScatterplotLayer` (nodos, radio+color por métrica),
  `LineLayer` (aristas, ancho/color por tráfico previsto), `ArcLayer`
  (importancia de aristas, **E1** se enciende en la propagación).
- **E5**: bucle de 24 h, día curado + selector de día, play/pause/scrub,
  lectura de hora + ticker meteo (Comunidad de Madrid). Toggle de horizonte
  now / +1h / +3h / +6h.
- **E7**: selector de métrica del color de nodo — tráfico | NO₂ | O₃ | ruido
  dB | **índice de salud 0-100** (por defecto), leyenda "bueno para pedalear
  / estar ahora".
- Sin interacción de ruta todavía (llega en `FIL_35`/`FIL_38`).

## Consecuencia asumida del stack

pydeck necesita red al visualizar (bundle deck.gl + tiles) → se sirve como
**URL en GitHub Pages**, no como artefacto de claude.ai ni 100 % offline.
Para la defensa: wifi de sala, o vendorizar el bundle + `python -m http.server`.
La tira PNG es el respaldo offline y la figura de la memoria.

## Coste

Cero AWS.

## Entregable / progreso

Milestone **M3** en `viz/PROGRESO_MAPA.md` — primer HTML **animado**
publicado. A partir de aquí cada milestone re-publica el mismo fichero, así
el entregable final se ve crecer.
