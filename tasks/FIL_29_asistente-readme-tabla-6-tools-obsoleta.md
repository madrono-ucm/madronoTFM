---
kind: fil
title: "asistente/README.md — sección 'Las 6 tools' con 3 marcadas NotImplementedError que llevan tiempo implementadas"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
---

## Resolución (2026-08-30)

`asistente/README.md` § "Las 6 `tools`" → "Las 10 `tools`": tabla reescrita
con las 10 reales (añadidas `disponibilidad_aparcamiento`, `eventos_cercanos`,
`opciones_movilidad` sin la columna falsa `NotImplementedError`, más las 4
`*_prevista` que ni aparecían: `calidad_aire_prevista`, `trafico_prevista`,
`afluencia_prevista`, `calidad_aire_prevista_grafo`). Nota de que ninguna
lanza excepción por falta de datos. Las menciones históricas a "las 6
originales" en las secciones de changelog se dejan (dicen explícitamente que
ya no hay `NotImplementedError`, no inducen a error).

> **Contexto**: encontrado en `VIC_20` (consistencia de documentación
> cruzada, `doc/PLAN-EVALUACION-TECNICA-2.md`).

## Qué está desactualizado (verificado)

`asistente/README.md`, sección `## Las 6 \`tools\` del agente MCP` (línea
250 en la versión actual), tiene una tabla con 6 filas donde **3 dicen
`NotImplementedError`**:

- `opciones_movilidad`
- `disponibilidad_aparcamiento`
- `eventos_cercanos`

**Las tres llevan mucho tiempo implementadas de verdad** — confirmado en
vivo en esta misma sesión (`VIC_16`): las 9 tools (incluidas estas 3, más
`calidad_aire_prevista`, `trafico_prevista` y `afluencia_prevista`, que ni
siquiera aparecen en la tabla) responden con datos reales de Athena/Neo4j,
tienen `output_schema`, `title` y `annotations` correctos, y están
cubiertas por tests reales. El propio fichero se ha editado varias veces
durante `FIL_13`–`15` (nuevas secciones añadidas, p. ej. "Envoltorio de
las tools de previsión") sin que nadie limpiara esta tabla vieja, que
parece datar de antes de las tareas 090/095/096.

## Por qué importa

Alguien que lea solo esta sección (el README del propio módulo, no la
memoria) se lleva la impresión de que la mitad de las tools del asistente
no existen — lo contrario de la realidad verificada.

## Qué hacer (propuesto, no aplicado aquí — no es un fix trivial de una
cifra, es reescribir la tabla completa)

Sustituir la tabla de 6 filas por una de 9, con estado real para cada
una (todas "real", con su fuente — Athena/Neo4j/ONNX según corresponda),
alineada con la tabla equivalente que ya existe en el `README.md` raíz
(`FIL_19`) y en `doc/VIKT-06-recorrido-e2e.md`. Revisar también si el
título de la sección "Por qué solo `calidad_aire` en esta tarea" (línea
55) sigue teniendo sentido como introducción histórica, o si necesita una
nota de que ya no es "la única".

## Restricciones

- No se ha editado `asistente/README.md` en este ticket.

## Criterios de aceptación

- La tabla de tools de `asistente/README.md` refleja las 9 tools reales,
  sin ningún `NotImplementedError` que ya no sea cierto.
