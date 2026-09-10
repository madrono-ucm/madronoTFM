---
kind: fil
title: "Umbrales OMS/UE de NO2/O3 duplicados en 4 ficheros sin módulo compartido"
owner: Sistema
status: pending
found_by: "VIC_39 (QA de calidad_aire_episodio)"
created_at: "2026-09-10"
---

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
