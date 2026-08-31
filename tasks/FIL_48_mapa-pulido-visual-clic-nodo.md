---
kind: fil
title: "Mapa animado — pulido visual (imagen más limpia) + restaurar el clic en nodo"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_47]
milestone: "M4c"
---

## Contexto

Tras `FIL_47` el mapa se lee mejor pero **seguía sintiéndose recargado**, y
la reescritura del `_TEMPLATE` **se dejó fuera el `onClick` del nodo** — ya
no se podía pinchar un punto para ver su detalle (el panel E4 quedó
inalcanzable salvo por el tooltip de hover).

## Resolución (2026-08-31) — `viz/build_mapa_animado.py`, `_TEMPLATE` + `_frame_strip_png`

### Clic en nodo (bug de `FIL_47`)
- `ScatterplotLayer#nodes` recupera `onClick` → fija `selNode`, cambia a la
  pestaña *arista/nodo* y renderiza el panel E4 (sparklines 24 h + aristas
  de importancia).
- **Anillo de selección**: capa `#sel` (un solo punto, `radiusUnits:"pixels"`,
  aro blanco sin relleno) marca el nodo elegido con nitidez.

### Imagen más limpia
- **Textura del grafo OFF por defecto** (era la mayor fuente de ruido);
  cuando se activa, opacidad 13→10 y color azulado tenue.
- **Nodos**: radio dependiente del zoom (`nodeRmin()`: 1.6 px de lejos →
  4.2 px de cerca) para que sean puntos nítidos y no una mancha; borde
  oscuro sutil (`getLineColor:[8,11,16,110]`); los nodos **sin dato** pasan
  de α110 a **α28** (casi invisibles, no ensucian).
- **Distritos**: relleno α6→3, línea gris-azulada α42→34 y más fina.
- **Arcos de importancia**: más planos (`getHeight` 0.4→0.16) y finos.
- **Etiquetas de distrito**: MAYÚSCULAS, más pequeñas (12→10), más tenues, y
  aún más si el zoom < 10.8.
- **Fondo**: degradado radial `#0e141c → #070a0e` en vez de plano `#0b0f14`.
- **Botón "vista limpia"**: apaga textura/arcos/etiquetas/hitos, atenúa el
  panel de control y oculta el de contexto → imagen de captura despejada.

### Tira de fotogramas (`viz/mapa_frames.png`, figura de la memoria)
Rehecha con estética de la app: fondo oscuro, 5 fotogramas
(04/08/13/18/22 h), puntos `s=11` legibles, contornos de distrito tenues,
barra de color sin marco, encuadre fijo al bbox de los nodos.

## Verificación

`node --check` sobre el JS; `tests/` en verde (+assert de `onClick` /
`id="clean"` / `#sel`). `viz/mapa/` regenerado y republicado a `gh-pages`
(`FIL_42`).
