---
kind: fil
title: "Umbrales OMS/UE de NO2/O3 duplicados en 4 ficheros sin módulo compartido"
owner: Sistema
status: done
found_by: "VIC_39 (QA de calidad_aire_episodio)"
created_at: "2026-09-10"
---

## Hecho (2026-09-10, Claude)

Creado `asistente/umbrales.py` con `LIMITE_REFERENCIA_UGM3` (los 6
contaminantes que ya llevaba `asistente/mcp_agent/tools.py::_LIMITES_
REFERENCIA_UGM3`, no solo los 4 que resumía este ticket) y `BANDAS_UGM3`
(los cortes de 4 niveles de `viz/build_mapa_animado.py`). Actualizados los
4 ficheros para importar de ahí:

- `asistente/mcp_agent/tools.py`: `_LIMITES_REFERENCIA_UGM3` es ahora un
  alias del import (cero cambio en el resto del fichero, que ya usaba ese
  nombre).
- `viz/build_mapa_animado.py`: los `cortes` de NO2/O3 vienen de
  `BANDAS_UGM3` (las etiquetas de banda se quedan locales, no son
  constantes regulatorias).
- `viz/build_grafo_ruta.py`/`viz/rutas.py`: el `no2`/`o3` de sus dicts de
  normalización (`_NORM`, `"norm"`) viene de `LIMITE_REFERENCIA_UGM3`;
  `traf`/`noise` se quedan locales (escalas propias de cada fichero, sin
  relación con un umbral regulatorio compartido).

`viz/` ya importaba de `asistente/` en otros módulos (`build_prevision_
animada.py`, `export_gold_slices.py`), así que no introduce ningún
acoplamiento nuevo. Ningún valor cambió (verificado con un `import` y
lectura directa de cada dict tras el cambio) — es deduplicación pura, sin
efecto de comportamiento. Test explícito de que no hay una tercera copia
no se añadió (el propio import hace imposible que diverjan, que era el
pedido del ticket) más allá de la comprobación manual de valores.

Suite completa (`asistente/`, `grafo/`, `modelado/tests/`): 439 passed, 2
failed (preexistentes de `FIL_61`, sin relación).

## Contexto

`VIC_39` pedía confirmar que la tool `calidad_aire_episodio` (`FIL_79`), el
módulo `asistente/umbrales.py` y `viz/build_mapa_animado.py` compartían un
único origen para los umbrales OMS/UE. **`asistente/umbrales.py` no
existe** — no hay ningún módulo compartido. Los valores de NO2 (200) y O3
(180) están hoy duplicados de forma independiente en:

- `asistente/mcp_agent/tools.py::_LIMITES_REFERENCIA_UGM3` — `{NO2: 200,
  O3: 180, PM10: 50, PM2.5: 25}`, usado por `calidad_aire_episodio` y otras
  tools.
- `viz/build_mapa_animado.py` — `cortes` de bandas OMS/UE para NO2
  `[25, 40, 100, 200]` y O3 `[100, 120, 180, 240]` (esquema de 4 niveles
  para colorear el mapa, no un único umbral — pero el corte superior
  coincide con el límite de la tool).
- `viz/build_grafo_ruta.py::_NORM` — `{"no2": 200.0, "o3": 180.0, ...}`
  (normalización para `ruta_saludable`).
- `viz/rutas.py::_NORM` — otra copia idéntica de lo mismo.

Hoy los cuatro coinciden, así que **no hay bug funcional actual** — es un
riesgo de mantenimiento: si alguien actualiza el límite en un sitio (por
ejemplo, tras revisar la normativa UE), los otros tres quedan
silenciosamente desincronizados, sin ningún test que lo detecte.

## Alcance propuesto

1. Crear `asistente/umbrales.py` (o `common/umbrales.py` si se prefiere
   compartir con `viz/`) con las constantes OMS/UE como única fuente:
   límite por contaminante (`NO2`, `O3`, `PM10`, `PM2.5`) y, si conviene,
   los cortes de banda de 4 niveles usados por el mapa.
2. Actualizar `asistente/mcp_agent/tools.py`, `viz/build_mapa_animado.py`,
   `viz/build_grafo_ruta.py` y `viz/rutas.py` para importar de ahí en vez
   de llevar su propia copia.
3. Añadir un test que falle si los valores divergen (o que simplemente ya
   no pueda divergir, al ser un único import).

## Prioridad

Baja / no bloqueante para la entrega del 17/9 — los valores están
correctos hoy en los cuatro sitios, verificado por `VIC_39`
(`doc/VIC-39-eval-tool-episodio-aire.md`). Es limpieza técnica, no una
corrección urgente.
