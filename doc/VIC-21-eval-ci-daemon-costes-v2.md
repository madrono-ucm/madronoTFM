# VIC-21 — Evaluación técnica ronda 2: refresco de CI/daemon/costes

Ejecutado 30/8, tras el volumen grande de PRs de `FIL_13`–`29`.

## CI

`gh run list` — todas las ejecuciones completadas en verde (`success`),
sin ningún reintento por fallo. Las únicas `in_progress` en el momento de
esta comprobación eran los propios commits de este ticket.

## `madrono-agent`

`systemctl is-active` → `inactive`, `is-enabled` → `disabled` (esperado,
congelación del 30/8). Último log antes de pararse: ciclos normales de
"no hay tareas pendientes, cola vacía" hasta un `Stopping`/`Deactivated
successfully` limpio — sin ningún error en el apagado.

## Coste

`herramientas/costes/desglose_glue.py`: **129,64 USD** acumulado (de los
cuales 23,07 USD sin resultado útil — FAILED/TIMEOUT/ERROR/STOPPED),
frente a ~124,27 USD de la comprobación anterior de esta sesión — subida
moderada y explicable por el volumen real de jobs de Glue de esta ronda
(backfill de `FIL_12`, verificaciones de `FIL_11`/`FIL_16`), no un pico
anómalo. Proporción de gasto desperdiciado (~18%) estable.

## Disco

`df -h /` → 9,9 GB libres (56% usado) — sin ningún resto de los entornos
temporales usados durante esta sesión (clones limpios de `VIKT_08`,
verificaciones de `FIL_23`/`FIL_20`, etc.), todos limpiados correctamente
tras su uso.

## Conclusión

Sin hallazgos. CI, daemon, coste y disco en buen estado tras el volumen
de esta ronda.
