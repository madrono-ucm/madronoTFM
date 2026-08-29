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
