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

## Actualización importante (Claude QA, `VIC_17`, 30/8) — antes de decidir, leer esto

Se ejecutó de verdad `run_all.py` hoy contra los paneles reales (que sí
incluyen las features exógenas de `ML_01`) para dar una respuesta con
evidencia, no solo con fechas de fichero. Resultado: **calidad del aire
rinde peor que la línea base hoy en 2 de 3 horizontes** (skill h1=-0,16,
h3=-0,13, h6=0,24 — frente al 0,29/0,58/0,68 publicado). Tráfico reproduce
razonablemente cerca (0,34/0,58/0,75 frente a 0,37/0,61/0,76).

Esto **cambia la recomendación** respecto a lo que sugería el hallazgo
original de este ticket ("puede que solo haga falta re-ejecutar
`run_all.py`"): el skill de calidad del aire es genuinamente **volátil
día a día** con esta ventana de datos (confirmado también por
`historial.csv` del cron real de esta madrugada, que rechazó promocionar
el modelo de hoy por la misma razón). Simplemente sustituir la Tabla 3 por
los números de hoy la dejaría **peor**, no mejor — cambiaría "el modelo
bate a la línea base" por "el modelo pierde a 1-3h", que tampoco sería
representativo, solo sería el número de otro día concreto.

**Recomendación**: en vez de un refresco puntual, considerar publicar el
skill medio (o un rango) del backtest incremental en vez de un solo día —
ver [`doc/VIC-17-eval-modelado-v2.md`](../doc/VIC-17-eval-modelado-v2.md)
para el detalle completo y los números exactos. Esto no cierra la
decisión de este ticket, la informa con evidencia nueva.

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

## Decisión final (31/8, aprobada por el usuario) y redacción exacta lista para aplicar

**Decisión tomada**: publicar el skill **medio + rango** del backtest
incremental en la Tabla 3, en vez de sustituirla por el número de un solo
día (opción descartada porque calidad del aire es genuinamente volátil
día a día, ver arriba) o dejarla con una nota de "está desactualizada" sin
más (opción descartada por dejar un número obsoleto en la tabla de
resultados principal).

**Números reales, calculados hoy** (`python -m modelado.evaluation.backtest
--panel modelado/_data/panel_{calidad_aire,trafico}.parquet --target ...`,
contra los paneles reales que ya incluyen las features exógenas de
`ML_01` — 9 cortes diarios de backtest incremental, 22–30 ago. 2026):

| Fuente | h | Tabla 3 actual (memoria) | Skill medio (rango), backtest 9 días |
|---|---|---|---|
| Calidad del aire | 1 | 0,29 | **0,07 (−0,31 a 0,36)** |
| Calidad del aire | 3 | 0,58 | **0,41 (−0,17 a 0,79)** |
| Calidad del aire | 6 | 0,68 | **0,56 (0,25 a 0,81)** |
| Tráfico | 1 | 0,37 | **0,32 (0,24 a 0,37)** |
| Tráfico | 3 | 0,61 | **0,53 (0,44 a 0,59)** |
| Tráfico | 6 | 0,76 | **0,67 (0,55 a 0,75)** |

Fuente de los números:
`modelado/evaluation/artifacts/backtest/backtest_{calidad_aire,trafico}.csv`
(regenerados hoy, `31/8`). `backtest_calidad_aire.csv` ya estaba trackeado
en git y se actualiza con este commit; `backtest_trafico.csv` es nuevo y
queda fuera del repo por el `.gitignore` existente de
`modelado/evaluation/artifacts/` (convención ya establecida del proyecto,
no cambiada aquí) — los números están transcritos completos en la tabla
de arriba, no hace falta el CSV para aplicar la redacción.

### Redacción exacta propuesta para `documents/Memoria_TFM FV.docx`

**1. Tabla 3 (§7.2)** — sustituir los 6 valores de skill por los de la
columna "Skill medio (rango)" de arriba, y añadir una nota al pie de
tabla (texto nuevo, no reemplaza nada):

> *Skill medio (LightGBM vs. mejor línea base) de un backtest incremental
> de 9 cortes diarios (22–30 de agosto de 2026), no de una única corrida
> puntual — el rango entre paréntesis refleja la varianza real día a día,
> especialmente marcada en calidad del aire a 1-3h (ver §7.4).*

**2. §7.5 (futuras líneas)** — el párrafo que motivó este ticket:

- **Dice hoy**: "Cerrar el hueco del feature store (`modelado/`):
  incorporar el join real con la previsión meteorológica de AEMET y los
  festivos reales del calendario laboral de Madrid, hoy sin implementar
  en el panel de entrenamiento."
- **Debería decir**: "El join real con la previsión meteorológica de
  AEMET y los festivos reales del calendario laboral de Madrid
  (`modelado/features/exogenas.py`, `modelado/features/build.py`) ya está
  implementado, testeado y forma parte del panel de entrenamiento real
  que produce la Tabla 3 (§7.2)."
- **Por qué**: el código y los tests ya existían (`VIC_12`); esta
  actualización confirma además que los paneles reales que alimentan la
  Tabla 3 publicada ya usan estas features (backtest de arriba, `mtime`
  real de los parquet). Frase movida de "limitación futura" a "resultado
  conseguido" — mismo patrón ya aplicado a otros puntos de §7.4/§7.5 en
  `doc/VIKT-09-consistencia-final.md`.

**Pendiente (fuera del alcance de Claude, bloqueo de `.docx` de esta
sesión)**: aplicar estos dos cambios al `.docx` real. El resto de este
ticket (investigación, verificación de datos) está completo — `status`
se deja en `pending` porque el criterio de aceptación real ("la memoria
refleja el estado real") requiere la edición humana del documento.
