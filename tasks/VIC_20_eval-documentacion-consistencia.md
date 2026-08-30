---
kind: vic-eval
title: "Evaluación técnica ronda 2 — consistencia cruzada de documentación"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de código en este ticket (fixes de documentación menores sí
se pueden aplicar directamente si son triviales y verificados, igual que
se ha hecho el resto de esta sesión con `doc/*.md`).

## Alcance

Cada documento (`README.md` raíz, `asistente/README.md`,
`modelado/README.md`, `infra/OPERACION.md`, `doc/README.md`) se ha editado
por separado durante `FIL_13`–`25`. Esta pasada busca contradicciones
**entre** ellos, no dentro de cada uno por separado:

- ¿El número de tools, el conteo de fuentes/productores, y el estado del
  pipeline (congelado) se dicen igual en los 5 documentos?
- ¿`doc/README.md` (índice de la bitácora) referencia algún `doc/NNN-*.md`
  que ya no existe, o le faltan entradas de los `FIL_*`/`VIKT_*` recientes?
- Enlaces internos rotos (`[texto](ruta)` a ficheros que no existen).
- Términos ya obsoletos que sobrevivan en más de un sitio (p. ej. "siete
  herramientas", si quedó en algún README aparte de la memoria).

## Criterios de aceptación

- Tabla de contradicciones encontradas (documento A dice X, documento B
  dice Y, cuál es la verdad real).
- Fixes triviales (una cifra, un enlace) aplicados directamente con
  evidencia del antes/después.
- Cualquier cosa que no sea trivial → ticket `FIL_*` nuevo.

## Restricciones

- No se edita `documents/Memoria_TFM FV.docx` en este ticket (eso es la
  pista `VIKT_*`, y además esta sesión tiene el `.docx` bloqueado por el
  clasificador de modo automático — ver `VIKT_09`/`VIKT_07`).
