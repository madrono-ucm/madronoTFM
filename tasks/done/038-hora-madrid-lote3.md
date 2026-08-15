---
id: 38
slug: hora-madrid-lote3
title: Hora de Madrid en timestamps — lote 3/3 (AEMET, CAMS, callejero, barrios, POI,
  calendario, CRTM)
status: done
force: true
allow_infra_apply: false
branch: task/038-hora-madrid-lote3
pr_number: 85
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/85
attempts: 6
next_retry_at: '2026-08-15T16:48:36.997457+00:00'
last_error: You've hit your session limit · resets 2:40pm (UTC)
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T16:58:50.045442+00:00'
started_at: '2026-08-15T10:45:22.899575+00:00'
submitted_at: '2026-08-15T16:57:43.809856+00:00'
merged_at: '2026-08-15T16:57:47Z'
---

## Contexto

Continúa las tareas 034-037 (mismo objetivo, ver su contexto; el lote 1 original
se dividió en dos tareas, 035 y 036, tras agotar presupuesto una vez). Lote 3 — al
terminar, los 21 módulos de `ingesta/capturas/` usarán hora de Madrid de forma
consistente.

## Objetivo

Sustituir el uso de UTC por hora de Madrid (`now_madrid()` de la tarea 034, o
conversión al `tzinfo` de `Europe/Madrid`) en:

| Módulo |
|---|
| `aemet_prevision_avisos.py` |
| `cams_calidad_aire_madrid.py` |
| `callejero_madrid.py` |
| `barrios_distritos_madrid.py` |
| `poi_madrid.py` |
| `calendario_laboral_madrid.py` |
| `crtm_red_transporte_madrid.py` |

No toques ningún otro módulo — los lotes 1 (035/036) y 2 (037) cubren el resto.

## Alcance concreto

1. Para cada uno de los 7 módulos, localiza los usos de `datetime.now(timezone.utc)`
   u otra conversión a UTC, y sustitúyelos por hora de Madrid.
2. Para los módulos de referencia estática (`callejero_madrid.py`,
   `barrios_distritos_madrid.py`, `poi_madrid.py`, `calendario_laboral_madrid.py`,
   `crtm_red_transporte_madrid.py`) el cambio probablemente solo afecta a
   `ingested_at` (no tienen `measured_at` con periodicidad propia) — confírmalo
   caso por caso.
3. Actualiza los tests que dependan del valor/formato de estos campos.
4. Actualiza la sección de cada módulo en `ingesta/README.md`.
5. Regenera la muestra commiteada de cada uno en `ingesta/capturas/samples/`
   ejecutando el módulo de verdad (dato real, no inventado a mano, salvo que la
   fuente no fuera accesible — mismo criterio que siempre). **AEMET y CAMS ya
   tienen credenciales reales en producción** (SSM, fijadas fuera de este
   pipeline) — pero esta EC2 no las tiene disponibles como variables de entorno
   locales; si `AEMET_API_KEY`/`CAMS_ADS_API_KEY` no están definidas en este
   entorno al ejecutar el módulo, la muestra seguirá marcada `is_mock: true`
   como hasta ahora, documenta que fue por eso y no por que las credenciales no
   existan en absoluto.

## Restricciones

- Alcance estrictamente estos 7 módulos.
- NO despliegues nada en AWS.
- Si alguno quedara bloqueado por algo imprevisto, documenta el motivo en
  `doc/038-hora-madrid-lote3.md` y continúa con el resto.

## Criterios de aceptación

- Los 7 módulos usan hora de Madrid en sus timestamps, verificado con una muestra
  real (o mock, para AEMET/CAMS) regenerada.
- `ingesta/README.md` actualizado para los 7.
- Todos los tests del proyecto siguen pasando.
