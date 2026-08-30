---
kind: vic-eval
title: "Evaluación técnica ronda 2 — asistente/ completo (9 tools, hardening MCP)"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de código en este ticket.

## Alcance

`VIC_11` (ronda 1) evaluó 7 tools antes de `FIL_13`–`15`/`24`. Esta pasada
cubre el estado actual completo:

- Las 9 tools registradas, no solo las que ya se probaron durante el
  aterrizaje de cada `FIL_*`.
- Calidad real de `asistente/tests/` (no solo que pasen — si cubren casos
  de fallo, límites, degradación).
- `asistente/models/` (`respuesta.py`, `herramientas.py`) — coherencia de
  tipos, herencia de `RespuestaPrevision`.
- Servidor MCP: transporte real (`stdio` + HTTP montado), `instructions`,
  `annotations`, `output_schema` de las 9 — verificar en vivo con un
  `ClientSession` real, no confiar solo en que los tests existentes pasen.
- Revisar si algún docstring/comentario quedó desalineado con el código
  tras las 3 rondas de PR de `FIL_15`.

## Criterios de aceptación

- Suite `asistente/` ejecutada y su cobertura evaluada cualitativamente
  (no solo el conteo de tests).
- Verificación en vivo (no solo tests) de al menos: transporte real,
  degradación bajo un fallo genuino, output_schema de las 9 tools.
- Cualquier hallazgo de código → ticket `FIL_*` nuevo, no aplicado aquí.

## Restricciones

- Región AWS: pasar `--region eu-west-1` explícito siempre.
- Neo4j: si las credenciales SSM siguen bloqueadas por el clasificador de
  esta sesión, documentarlo como limitación explícita, sin rodeos.

## Hecho (30/8)

Ver [`doc/VIC-16-eval-asistente-v2.md`](../doc/VIC-16-eval-asistente-v2.md).
Nuevo en esta pasada: transporte HTTP real (`uvicorn` + `curl`, nunca
probado en vivo hasta ahora), revisión de `asistente/models/` (coherencia
de herencia/contenedores, sin colisiones). Dos hallazgos menores
observacionales (docstring desactualizado, conteo de tests del commit de
`FIL_14` impreciso) — ninguno amerita ticket `FIL_*`. Sin hallazgos de
código que requieran cambio.
