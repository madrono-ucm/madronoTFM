---
id: 36
slug: hora-madrid-lote2
title: "Hora de Madrid en timestamps — lote 2/3 (agenda eventos, recintos, afluencia, aforos, Bluesky, cines)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-15T09:49:55+00:00"
updated_at: "2026-08-15T09:49:55+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Continúa las tareas 034/035 (mismo objetivo, ver su contexto). Lote 2 de 3.

## Objetivo

Sustituir el uso de UTC por hora de Madrid (`now_madrid()` de la tarea 034, o
conversión al `tzinfo` de `Europe/Madrid`) en:

| Módulo |
|---|
| `agenda_eventos_madrid.py` |
| `agenda_recintos_madrid.py` |
| `afluencia_lugares_madrid.py` |
| `aforos_peatones_bicicletas_madrid.py` |
| `bluesky_menciones_madrid.py` |
| `cartelera_cines_madrid.py` |

No toques ningún otro módulo — el lote 1 (035) y el lote 3 (037) cubren el resto.

## Alcance concreto

1. Para cada uno de los 6 módulos, localiza los usos de `datetime.now(timezone.utc)`
   u otra conversión a UTC, y sustitúyelos por hora de Madrid.
2. Actualiza los tests que dependan del valor/formato de estos campos.
3. Actualiza la sección de cada módulo en `ingesta/README.md`.
4. Regenera la muestra commiteada de cada uno en `ingesta/capturas/samples/`
   ejecutando el módulo de verdad (dato real, no inventado a mano, salvo que la
   fuente no fuera accesible — mismo criterio que siempre).

## Restricciones

- Alcance estrictamente estos 6 módulos.
- NO despliegues nada en AWS.
- Si alguno quedara bloqueado por algo imprevisto, documenta el motivo en
  `doc/036-hora-madrid-lote2.md` y continúa con el resto.

## Criterios de aceptación

- Los 6 módulos usan hora de Madrid en sus timestamps, verificado con una muestra
  real regenerada.
- `ingesta/README.md` actualizado para los 6.
- Todos los tests del proyecto siguen pasando.
