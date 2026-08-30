---
kind: vic-eval
title: "Evaluación técnica ronda 2 — refresco de CI/daemon/costes (VIC_14)"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de código en este ticket.

## Alcance

`VIC_14` verificó esto el 29/8, antes del volumen grande de PRs de
`FIL_13`–`25`. Refresco rápido:

- `gh run list` — ¿todos los checks de esta ronda de PRs están en verde?
  ¿alguno falló y se re-intentó?
- `journalctl -u madrono-agent` — sigue parado por la congelación
  (esperado), confirmar que no hay ningún error inesperado en su último
  log antes de pararse.
- `herramientas/costes/desglose_glue.py` — coste real actualizado; ¿el
  volumen de nuevos jobs de Glue disparados por los PRs de esta ronda
  (o el propio backfill de `FIL_12`) se nota en la curva?
- `df -h /` en esta EC2 — tras varias auditorías con instalaciones
  temporales de `torch`/CUDA en esta sesión, confirmar que no quedó nada
  sin limpiar.

## Criterios de aceptación

- Estado real de CI, daemon, coste y disco documentado con comandos y
  salida reales.
- Cualquier hallazgo → ticket `FIL_*` nuevo.

## Hecho (30/8)

Ver [`doc/VIC-21-eval-ci-daemon-costes-v2.md`](../doc/VIC-21-eval-ci-daemon-costes-v2.md).
CI 100% verde, daemon parado limpiamente, coste 129,64 USD (subida
moderada y explicable), disco sin restos de esta sesión. Sin hallazgos.
