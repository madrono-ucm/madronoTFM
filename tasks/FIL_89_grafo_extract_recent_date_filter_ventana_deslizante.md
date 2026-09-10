---
kind: fil
title: "grafo/extract.py: _recent_date_filter usa current_date real -> se queda sin datos ~13/9, antes de la entrega"
owner: Claude (QA, VIC_35)
status: pending
depends_on: [FIL_84]
created_at: "2026-09-10"
---

## Contexto

Encontrado al revisar el punto 6 de `VIC_35`. `grafo/extract.py::
_recent_date_filter()` acota varias consultas de Athena a los últimos
`_RECENT_WINDOW_DAYS = 14` días **respecto al reloj real de Athena**
(`current_date`), no respecto a una fecha ancla fija:

```python
def _recent_date_filter(column: str = "date") -> str:
    return (
        f"{column} >= date_format(date_add('day', -{_RECENT_WINDOW_DAYS}, current_date), '%Y-%m-%d')"
    )
```

La ingesta está **congelada desde 2026-08-30** (última fecha real con
datos en Gold: ~29-30/8) — decisión deliberada del equipo, ver
`NEXT_STEPS.md`/`PROGRESS.md`. Como la ventana es deslizante sobre el reloj
real y no sobre esa fecha congelada, cada día que pasa sin que se
reanude la ingesta la ventana avanza mientras los datos reales se quedan
fijos. Verificado con la fecha real del sistema hoy (2026-09-10):

| Fecha de ejecución | Ventana (`current_date - 14d` .. hoy) | ¿Incluye 29-30/8? |
|---|---|---|
| 2026-09-10 (hoy) | 27/8 – 10/9 | Sí |
| 2026-09-13 | 30/8 – 13/9 | Al límite (justo 30/8) |
| 2026-09-14 | 31/8 – 14/9 | **No** |
| 2026-09-17 (entrega) | 3/9 – 17/9 | **No, ventana vacía de datos reales** |

**Funciones afectadas** (todas usan `_recent_date_filter()`):
`fetch_estaciones_trafico` (`subarea`), `fetch_estaciones_calidad_aire`
(`contaminantes`), `fetch_estaciones_ruido`, `fetch_paradas_emt`,
`fetch_paradas_bicimad` (`anclajes_totales`), `fetch_lugares_aparcamientos`
(`plazas_totales`), `fetch_lugares_cartelera_cines`,
`fetch_recintos_eventos_silver`. (`fetch_estaciones_meteo` y
`fetch_estaciones_aforos_peatones_bicicletas` ya están exentas
explícitamente, con nota en el código — no aplica a esas.)

## Impacto

No afecta las tools del asistente en producción (leen del grafo ya
cargado, con valores estáticos guardados en cada nodo — la ventana solo
se evalúa en el momento de la **carga/recarga** del grafo). El riesgo es
concreto: si alguien ejecuta `grafo.cargar_grafo` (o cualquier `fetch_*`
de este módulo) en o después del **13-14 de septiembre** — plausible
como "recarga final antes de la defensa" — las consultas con
`_recent_date_filter()` empezarán a perder filas silenciosamente
(`GROUP BY` sobre un `WHERE` cada vez más vacío, sin error, sin
excepción) y para el 17/9 devolverían 0 filas: una recarga en el peor
momento posible borraría atributos reales (`contaminantes`, `subarea`,
capacidades) de nodos que ya los tenían, sin ningún aviso.

`FIL_84` ya resolvió exactamente esta misma clase de problema para las
tools del asistente (`ASSISTANT_ANCHOR_DATE` / `DIAS_CURADOS` en
`asistente/timeutils.py`) — este módulo (`grafo/extract.py`) es un código
distinto que no se tocó en ese ticket y tiene el mismo problema de fondo.

## Alcance propuesto (sin implementar todavía — solo detectado en QA)

- Anclar `_recent_date_filter()` a una fecha fija configurable (env var,
  mismo patrón que `ASSISTANT_ANCHOR_DATE`, o un valor por defecto
  hardcodeado a la fecha de congelación conocida) en vez de
  `current_date` de Athena, **o** ampliar `_RECENT_WINDOW_DAYS` no es
  suficiente por sí solo (solo retrasa el problema).
- Alternativa más simple: quitar el filtro de fecha por completo para
  estas consultas de atributos estáticos (igual que ya se hizo para
  meteo/aforos) — son atributos que cambian poco y el coste de escanear
  Gold completo ya se paga en otras `fetch_*` sin filtro.
- Cualquiera de las dos opciones necesita repetir la carga real del
  grafo (`grafo.cargar_grafo`) para confirmar que las cifras de `VIC_34`
  (23/23 contaminantes, 4413/4705 subarea, etc.) se mantienen con el
  fix aplicado.

## Criterios de aceptación

- `_recent_date_filter()` (o su reemplazo) no depende de cuándo se
  ejecuta la consulta, solo de la fecha de los datos reales.
- Una recarga del grafo ejecutada el 17/9 da los mismos resultados que
  una ejecutada hoy (verificable con un test que fije `current_date`
  simulado, o con una recarga real antes y después si hay margen).
- No se cambia el comportamiento para `fetch_estaciones_meteo`/
  `fetch_estaciones_aforos_peatones_bicicletas` (ya sin filtro, a
  propósito).
