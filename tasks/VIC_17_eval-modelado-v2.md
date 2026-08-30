---
kind: vic-eval
title: "Evaluación técnica ronda 2 — modelado/ (export STGNN real desde registry, Tabla 3)"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de código en este ticket.

## Alcance

`FIL_20` verificó el export del STGNN de forma **sintética** (modelo
recién creado en el test, no el `@champion` real del registry). Esta
pasada:

- Ejecutar `exportar_stgnn_desde_registry` (o el `--stgnn` del CLI) contra
  el registry MLflow **real** de esta EC2 (`modelado/mlflow.db`) si existe
  un `@champion` de STGNN, y verificar la paridad con datos reales, no
  sintéticos.
- Revisar `modelado/export/CONTRATO.md` tras la reescritura de `FIL_20` —
  ¿el contrato de entrada/salida documentado coincide con lo que de verdad
  produce el exportador?
- **Tabla 3**: `VIKT_05`/`VIKT_09` encontraron que los números publicados
  no reproducen con el código actual (calidad del aire 3–5,6x distinto).
  Esta pasada no re-investiga la causa (ya está diagnosticada) sino que
  aporta una recomendación operativa concreta: ¿merece la pena, dado el
  tiempo hasta la entrega (17/9), volver a ejecutar
  `modelado.evaluation.estudios.run_all` ahora mismo y dejar el resultado
  listo para que `VIKT_05` solo tenga que decidir pegarlo?
- Confirmar que la suite `modelado/tests/` (incluido el nuevo
  `test_ml07.py::StgnnOnnxExportTests`) sigue en verde con el entorno
  actual (torch CPU tras `FIL_23`).

## Criterios de aceptación

- Export STGNN verificado contra el registry real si hay un `@champion`
  disponible (documentar si no lo hay, sin inventar uno).
- Recomendación explícita y accionable sobre Tabla 3 (no solo "es un
  problema", sino "hacer X ahora mismo cuesta Y, aporta Z").
- Cualquier hallazgo de código → ticket `FIL_*` nuevo.

## Restricciones

- No re-entrenar modelos "a ojo" para forzar una Tabla 3 distinta — si se
  recomienda refrescarla, que sea con `run_all.py` tal cual existe.
