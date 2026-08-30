---
kind: vikt
title: "Memoria §7.5 — el gap de ML_01 (meteo/festivos) ya no está sin implementar"
owner: Pista Memoria — documentación (interactivo)
status: pending
created_at: "2026-08-29"
depends_on: [VIC_12, VIC_15]
---

## Contexto

`VIC_12`/`VIC_15` (evaluación técnica, `doc/PLAN-EVALUACION-TECNICA.md`)
encontraron que `documents/Memoria_TFM FV.docx` §7.5 (futuras líneas) dice:

> "Cerrar el hueco del feature store (`modelado/`): incorporar el join real
> con la previsión meteorológica de AEMET y los festivos reales del
> calendario laboral de Madrid, hoy sin implementar en el panel de
> entrenamiento."

Esta frase la escribió `VIKT_03` el 29/8, correcta en su momento. Desde
entonces, otra sesión (sin ticket `ML_*`/`FIL_*` propio que lo documente)
añadió `modelado/features/exogenas.py` (join real de meteo observada +
previsión AEMET, "la previsión de ayer para hoy", sin fuga) y festivos
reales del calendario laboral en `modelado/features/build.py`
(`_cargar_festivos`), ambos con tests reales (`test_exogenas.py`,
`test_build.py`, verificados en verde en `VIC_12`).

## Matiz importante — no basta con borrar la frase

El código existe y está testeado, **pero no está confirmado que los
modelos que producen la Tabla 3 actual de la memoria (§7.2) se hayan
reentrenado con estas features nuevas** — `VIC_12` solo verificó que el
código y los tests existen, no volvió a entrenar nada. Antes de tocar la
memoria:

1. Confirmar si `comparacion_todos.csv` (fuente de la Tabla 3) se generó
   con o sin estas features exógenas nuevas (mirar fecha del fichero vs
   fecha del commit de `exogenas.py`, o simplemente volver a correr
   `modelado.evaluation.estudios.run_all` y comparar).
2. Si la Tabla 3 **no** las incluye todavía: la redacción correcta no es
   "ya está resuelto", es algo más matizado — el código y los tests están
   listos, pero los resultados publicados en la memoria son de antes de
   esta mejora. Decidir si merece la pena volver a entrenar antes del
   cierre (17/9) para que la Tabla 3 las incluya, o dejarlo para después
   de la entrega.
3. Si la Tabla 3 **sí** las incluye ya (quizás se reentrenó sin que quede
   registrado en ningún ticket): entonces sí, quitar la frase de §7.5 y
   mencionar el join real en la sección de metodología/datos que
   corresponda (§6.1/§6.2, ya escritas por `VIC_02`).

## Qué hacer

- Investigar el punto anterior (fecha de los artefactos vs fecha del
  código) antes de decidir qué redacción usar.
- Editar `documents/Memoria_TFM FV.docx` con `python-docx` (coordinar el
  turno del `.docx`, ver `PLAN.md`) según lo que se confirme.
- Si se decide reentrenar antes de tocar la memoria, ese reentrenamiento
  es trabajo de la pista `ML_*`/`FIL_*`, no de este ticket.

## Criterios de aceptación

- La memoria refleja el estado real y verificado (no solo "existe código")
  de las features exógenas de `ML_01`.
- Estilos/numeración del `.docx` intactos.

## Investigación del punto 1 (Claude QA, 30/8)

Respuesta al matiz del punto 1: **la Tabla 3 actual NO se entrenó con las
features exógenas nuevas** — verificado comparando fechas reales, no
supuestas:

- `modelado/_data/panel_trafico.parquet`/`panel_calidad_aire.parquet` (los
  paneles que consume `modelado/evaluation/estudios/run_all.py` vía
  `pd.read_parquet`, sin volver a llamar a `build.py` en el propio
  `run_all.py`) tienen `mtime` real **2026-08-30 03:30 UTC**, y de hecho ya
  contienen las columnas exógenas nuevas (`meteo_temperature_c`,
  `meteo_humidity_pct`, `meteo_wind_speed_ms`, `meteo_precipitation_lm2`,
  `meteo_pressure_mb`, `es_festivo` — confirmado leyendo el parquet con
  `pandas`, no solo mirando el nombre del fichero).
- Pero `modelado/evaluation/artifacts/estudios/comparacion_trafico.csv` (la
  fuente real de la Tabla 3, vía `estudio_comparacion.tabla_comparacion`)
  tiene `mtime` **2026-08-29 18:01:57 UTC** — **anterior** tanto a la
  regeneración de esos paneles (30/8 03:30) como al propio commit de
  `ML_01` (`5a89ef3`, `2026-08-29T19:04:11 UTC`).

Es decir: alguien (probablemente el cron nocturno de `ML_10`, que sí
reconstruye paneles) regeneró los paneles Tier 1 con las nuevas features
exógenas **después** de que se generaran los CSV de comparación que
alimentan la Tabla 3 — pero nadie ha vuelto a ejecutar
`python -m modelado.evaluation.estudios.run_all` desde entonces. La Tabla 3
publicada en la memoria sigue siendo la de **antes** de `ML_01`.

**Conclusión para la redacción** (según el punto 2 de este ticket): la
frase correcta NO es "ya está resuelto" ni tampoco dejar la frase original
de §7.5 tal cual (que dice "sin implementar", lo cual ya no es cierto para
el código) — hace falta una redacción intermedia: el join de meteo/festivos
**ya existe, está testeado y ya forma parte del panel de entrenamiento
real**, pero **la Tabla 3 publicada todavía no se reentrenó con él**. Antes
de editar el `.docx`, decidir (fuera de este ticket, con Filippos/Víctor):
volver a correr `run_all.py` (barato, son paneles ya materializados, no
hace falta re-ingestar nada) para refrescar la Tabla 3 con las features
nuevas antes del 17/9, o documentar explícitamente en §7.4/§7.5 que la
Tabla 3 es anterior a este cierre de gap. No se ha tocado
`documents/Memoria_TFM FV.docx` en este ticket.
