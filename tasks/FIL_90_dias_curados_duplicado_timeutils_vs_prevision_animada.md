---
kind: fil
title: "DIAS_CURADOS duplicado en asistente/timeutils.py y viz/build_prevision_animada.py sin módulo compartido"
owner: Sistema
status: pending
found_by: "VIC_44 (QA de anclaje temporal, FIL_84)"
created_at: "2026-09-10"
---

## Contexto

`VIC_44` pedía confirmar que `asistente/timeutils.py::DIAS_CURADOS` coincide
exactamente con las copias de `viz/build_mapa_animado.py` y
`asistente/modelos/grafo_ruta.json`. Los tres coinciden hoy
(`2026-08-19`, `2026-08-23`, `2026-08-26`, mismo orden), pero:

- `asistente/modelos/grafo_ruta.json` es un **artefacto generado**, no una
  segunda definición — su campo `dias` viene de
  `viz/build_prevision_animada.py::DIAS` en tiempo de construcción, no es
  independiente.
- `viz/build_prevision_animada.py` **sí** tiene su propia definición
  independiente: `DIAS = ("2026-08-19", "2026-08-23", "2026-08-26")`
  (línea 56), con el mismo comentario explicativo que
  `asistente/timeutils.py::DIAS_CURADOS` pero sin importarlo de ahí ni al
  revés. Dos fuentes de verdad para el mismo trío de fechas — mismo patrón
  que `FIL_87` (umbrales OMS/UE duplicados en 4 ficheros), ya arreglado hoy
  con `asistente/umbrales.py`.
- `viz/build_mapa_animado.py` además incrusta dos de las tres fechas como
  literales de texto sueltos (línea 331, frame de previsualización por
  defecto; líneas 1105-1106, un pie de un tour guiado) — no son una
  "definición" per se, pero si `DIAS_CURADOS` cambiara algún día, estos dos
  sitios habría que tocarlos a mano y es fácil olvidarlos.

Ningún bug funcional hoy — los tres coinciden, verificado por `VIC_44`.

## Alcance propuesto

1. Elegir una fuente única: `asistente/timeutils.py::DIAS_CURADOS` es la
   candidata natural (ya la consume el asistente en producción); o mover
   el trío a un módulo neutral que ambos (`asistente/` y `viz/`) importen,
   igual que se hizo con `asistente/umbrales.py` en `FIL_87` -- `viz/` ya
   importa de `asistente/` en varios sitios
   (`build_prevision_animada.py::from asistente import prevision_grafo`,
   `export_gold_slices.py`), así que `viz/build_prevision_animada.py`
   podría simplemente importar `DIAS_CURADOS` de `asistente.timeutils` en
   vez de mantener su propio `DIAS`.
2. Actualizar `viz/build_prevision_animada.py` para importar en vez de
   redefinir.
3. Los dos literales sueltos de `viz/build_mapa_animado.py` (línea 331,
   líneas 1105-1106) son contenido narrativo (un frame por defecto, un pie
   de tour) más que una fuente de verdad -- documentarlos con un comentario
   que remita a `DIAS_CURADOS` es suficiente, no hace falta parametrizarlos
   si el coste de tocarlos a mano cuando cambien es bajo (son solo 2
   sitios, ambos ya cerca uno del otro en el fichero).
4. Añadir un test que falle si `viz/build_prevision_animada.DIAS` y
   `asistente.timeutils.DIAS_CURADOS` divergen (o que ya no pueda divergir,
   si se opta por el import).

## Prioridad

Baja / no bloqueante para la entrega del 17/9 -- los tres coinciden hoy,
verificado por `VIC_44`. Es limpieza técnica, mismo criterio de prioridad
que `FIL_87`.
