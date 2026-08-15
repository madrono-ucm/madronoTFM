---
id: 35
slug: hora-madrid-lote1
title: Hora de Madrid en timestamps — lote 1a (tráfico, EMT, BiciMAD, aparcamientos)
status: in_review
force: true
allow_infra_apply: false
branch: task/035-hora-madrid-lote1
pr_number: 82
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/82
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T10:27:22.320760+00:00'
started_at: '2026-08-15T10:20:03.941894+00:00'
submitted_at: '2026-08-15T10:27:22.320737+00:00'
merged_at: null
---

## Contexto

Continúa la tarea 034 (que ya añadió `now_madrid()` y corrigió el particionado de
`BronzeWriter`). Esta tarea corrige los campos de timestamp (`ingested_at`,
`measured_at` y cualquier otro campo de fecha/hora) de 4 productores de alta
frecuencia, ya en producción real, para que usen hora de Madrid en vez de UTC.

**Nota**: un primer intento de este lote cubría 7 productores de una vez y agotó
el presupuesto por tarea ($6, ~14.7M tokens) sin comitear nada — regenerar
muestras reales en vivo para varios productores a la vez resultó más caro de lo
esperado. Se redujo a 4; los otros 3 (calidad del aire, meteorología, ruido)
están en la tarea 036, creada aparte.

**Alcance acotado a propósito** — no lo amplíes a los demás productores, están en
las tareas 036/037/038.

## Objetivo

Sustituir, en cada uno de estos 4 módulos, el uso de `datetime.now(timezone.utc)`
(o cualquier conversión explícita a UTC de un timestamp de origen) por
`now_madrid()`/una conversión a `Europe/Madrid`:

| Módulo | Nota |
|---|---|
| `trafico_madrid.py` | `measured_at` hoy se documenta como "hora de Madrid convertida a UTC" — invierte esa conversión (quédate en hora de Madrid, no la conviertas a UTC) |
| `transporte_publico_madrid.py` | |
| `bicimad.py` | |
| `aparcamientos_madrid.py` | |

## Alcance concreto

1. Para cada uno de los 4 módulos, localiza todos los usos de
   `datetime.now(timezone.utc)`, `timezone.utc` en conversiones, o comentarios/
   código que asuma UTC como destino, y sustitúyelos por `now_madrid()` (importada
   de `bronze.py` o donde haya quedado tras la tarea 034) o por una conversión al
   `tzinfo` de `Europe/Madrid` cuando el timestamp venga de la fuente en otra
   zona horaria.
2. Actualiza los tests de cada módulo que dependan del valor/formato de estos
   campos (offset esperado, etc.).
3. Actualiza la sección de cada módulo en `ingesta/README.md` (donde diga
   "convertido a UTC", corrígelo a "convertido a hora de Madrid" o equivalente).
4. Regenera la muestra commiteada de cada uno de los 4 en
   `ingesta/capturas/samples/` ejecutando el módulo de verdad, para que el
   fixture también refleje el cambio (mismo criterio que cuando se crearon:
   dato real, no inventado a mano, salvo que la fuente no fuera accesible). Para
   `transporte_publico_madrid.py`, las credenciales reales ya están disponibles
   en `EMT_CLIENT_ID`/`EMT_PASS_KEY` si este entorno las tiene configuradas.

## Restricciones

- Alcance estrictamente estos 4 módulos — no adelantes trabajo de la 036, aunque
  parezca poco esfuerzo adicional: mantener el alcance pequeño es precisamente lo
  que evita repetir el fallo por presupuesto agotado.
- NO toques `bronze.py` (ya está resuelto en la 034) ni despliegues nada en AWS.
- Si algún módulo quedara bloqueado por algo imprevisto, documenta el motivo en
  `doc/035-hora-madrid-lote1.md` y continúa con el resto.

## Criterios de aceptación

- Los 4 módulos usan hora de Madrid en sus timestamps, verificado con una muestra
  real regenerada.
- `ingesta/README.md` actualizado para los 4.
- Todos los tests del proyecto siguen pasando.
