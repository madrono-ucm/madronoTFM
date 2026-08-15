---
id: 36
slug: hora-madrid-lote1b
title: Hora de Madrid en timestamps — lote 1b (calidad del aire, meteorología, ruido)
status: in_progress
force: true
allow_infra_apply: false
branch: task/036-hora-madrid-lote1b
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T10:10:00+00:00'
updated_at: '2026-08-15T10:30:31.872936+00:00'
started_at: '2026-08-15T10:30:31.872914+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa las tareas 034/035 (mismo objetivo, ver su contexto). Este lote nació de
dividir el lote 1 original (7 productores) en dos tareas más pequeñas tras agotar
presupuesto una vez intentándolos todos juntos ($6, ~14.7M tokens, sin comitear
nada). Esta es la segunda mitad, con los 3 productores restantes de alta
frecuencia, ya en producción real.

**Alcance acotado a propósito** — no lo amplíes a otros productores, están en las
tareas 037/038.

## Objetivo

Sustituir, en cada uno de estos 3 módulos, el uso de `datetime.now(timezone.utc)`
(o cualquier conversión explícita a UTC de un timestamp de origen) por
`now_madrid()`/una conversión a `Europe/Madrid`:

| Módulo |
|---|
| `calidad_aire_madrid.py` |
| `meteorologia_madrid.py` |
| `ruido_madrid.py` |

## Alcance concreto

1. Para cada uno de los 3 módulos, localiza todos los usos de
   `datetime.now(timezone.utc)`, `timezone.utc` en conversiones, o comentarios/
   código que asuma UTC como destino, y sustitúyelos por `now_madrid()` (importada
   de `bronze.py` o donde haya quedado tras la tarea 034) o por una conversión al
   `tzinfo` de `Europe/Madrid` cuando el timestamp venga de la fuente en otra
   zona horaria.
2. Actualiza los tests de cada módulo que dependan del valor/formato de estos
   campos (offset esperado, etc.).
3. Actualiza la sección de cada módulo en `ingesta/README.md` (donde diga
   "convertido a UTC", corrígelo a "convertido a hora de Madrid" o equivalente).
4. Regenera la muestra commiteada de cada uno de los 3 en
   `ingesta/capturas/samples/` ejecutando el módulo de verdad, para que el
   fixture también refleje el cambio (dato real, no inventado a mano, salvo que
   la fuente no fuera accesible).

## Restricciones

- Alcance estrictamente estos 3 módulos — no adelantes trabajo de la 037/038,
  aunque parezca poco esfuerzo adicional: mantener el alcance pequeño es
  precisamente lo que evita repetir el fallo por presupuesto agotado.
- NO toques `bronze.py` (ya está resuelto en la 034) ni despliegues nada en AWS.
- Si algún módulo quedara bloqueado por algo imprevisto, documenta el motivo en
  `doc/036-hora-madrid-lote1b.md` y continúa con el resto.

## Criterios de aceptación

- Los 3 módulos usan hora de Madrid en sus timestamps, verificado con una muestra
  real regenerada.
- `ingesta/README.md` actualizado para los 3.
- Todos los tests del proyecto siguen pasando.
