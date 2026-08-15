---
id: 35
slug: hora-madrid-lote1
title: Hora de Madrid en timestamps — lote 1/3 (tráfico, EMT, BiciMAD, aparcamientos,
  aire, meteo, ruido)
status: in_progress
force: true
allow_infra_apply: false
branch: task/035-hora-madrid-lote1
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T09:59:09.903332+00:00'
started_at: '2026-08-15T09:59:09.903309+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la tarea 034 (que ya añadió `now_madrid()` y corrigió el particionado de
`BronzeWriter`). Esta tarea corrige los campos de timestamp (`ingested_at`,
`measured_at` y cualquier otro campo de fecha/hora) de los 7 productores de mayor
frecuencia, ya en producción real, para que usen hora de Madrid en vez de UTC.

**Alcance acotado a propósito** (lote 1 de 3) — no lo amplíes al resto de
productores, están en las tareas 036/037.

## Objetivo

Sustituir, en cada uno de estos 7 módulos, el uso de `datetime.now(timezone.utc)`
(o cualquier conversión explícita a UTC de un timestamp de origen) por
`now_madrid()`/una conversión a `Europe/Madrid`:

| Módulo | Nota |
|---|---|
| `trafico_madrid.py` | `measured_at` hoy se documenta como "hora de Madrid convertida a UTC" — invierte esa conversión (quédate en hora de Madrid, no la conviertas a UTC) |
| `transporte_publico_madrid.py` | |
| `bicimad.py` | |
| `aparcamientos_madrid.py` | |
| `calidad_aire_madrid.py` | |
| `meteorologia_madrid.py` | |
| `ruido_madrid.py` | |

## Alcance concreto

1. Para cada uno de los 7 módulos, localiza todos los usos de
   `datetime.now(timezone.utc)`, `timezone.utc` en conversiones, o comentarios/
   código que asuma UTC como destino, y sustitúyelos por `now_madrid()` (importada
   de `bronze.py` o donde haya quedado tras la tarea 034) o por una conversión al
   `tzinfo` de `Europe/Madrid` cuando el timestamp venga de la fuente en otra
   zona horaria.
2. Actualiza los tests de cada módulo que dependan del valor/formato de estos
   campos (offset esperado, etc.).
3. Actualiza la sección de cada módulo en `ingesta/README.md` (donde diga
   "convertido a UTC", corrígelo a "convertido a hora de Madrid" o equivalente).
4. Regenera la muestra commiteada de cada uno de los 7 en
   `ingesta/capturas/samples/` ejecutando el módulo de verdad, para que el
   fixture también refleje el cambio (mismo criterio que cuando se crearon:
   dato real, no inventado a mano, salvo que la fuente no fuera accesible).

## Restricciones

- Alcance estrictamente estos 7 módulos.
- NO toques `bronze.py` (ya está resuelto en la 034) ni despliegues nada en AWS.
- Si algún módulo quedara bloqueado por algo imprevisto, documenta el motivo en
  `doc/035-hora-madrid-lote1.md` y continúa con el resto.

## Criterios de aceptación

- Los 7 módulos usan hora de Madrid en sus timestamps, verificado con una muestra
  real regenerada.
- `ingesta/README.md` actualizado para los 7.
- Todos los tests del proyecto siguen pasando.
