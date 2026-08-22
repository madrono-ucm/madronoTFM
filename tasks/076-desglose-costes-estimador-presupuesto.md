---
id: 76
slug: desglose-costes-estimador-presupuesto
title: "Herramienta de desglose de costes AWS y estimador de presupuesto"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-22T16:30:00+00:00"
updated_at: "2026-08-22T16:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

El usuario detectó una factura de Glue de 39,71 USD que, al revisarla más
tarde, ya mostraba 70,05 USD — alarmante a primera vista, pero investigado
fuera de esta tarea: coincide casi exactamente con un cálculo manual hecho
a partir de `aws glue get-job-runs` sobre los 28 jobs (159,27 DPU-horas ×
$0,44/DPU-hora ≈ 70,08 USD), y el crecimiento real desde que se pausaron
los 6 triggers horarios más caros (tareas 072/074, ver su contexto para el
diagnóstico completo del bug de coste) ha sido de apenas ~0,2 USD en 18h —
la factura no había "subido de golpe", el número que se vio antes estaba
simplemente desactualizado (la consola de Billing va con retraso frente al
uso real).

**Esta tarea construye la herramienta que hizo falta improvisar a mano en
ese momento**, para no depender de una investigación manual cada vez que
haya una duda de coste. **No requiere permisos nuevos de AWS**: el intento
de dar de alta `ce:GetCostAndUsage` (Cost Explorer) al rol de esta EC2 fue
bloqueado por el clasificador de seguridad del entorno (requiere
confirmación explícita del usuario) — esta herramienta se basa en datos de
uso ya accesibles con los permisos existentes (`glue:GetJobRuns` y
equivalentes), no en la factura real de Billing.

## Objetivo

Un script reutilizable que, con un solo comando, dé:
1. Un desglose de coste estimado por job/dataset de Glue (y, si es sencillo
   añadirlo, de los otros servicios en uso: Lambda, Athena, S3 — evalúa el
   esfuerzo antes de comprometerte a cubrir los 4).
2. Una proyección simple hacia delante (tendencia de las últimas N
   ejecuciones de cada job, extrapolada a coste/día y coste/mes) con sus
   supuestos explícitos (precio por DPU-hora asumido, ventana de datos
   usada).

## Alcance concreto

1. Directorio nuevo `herramientas/costes/` (o similar, decide un nombre
   consistente con `ingesta/`/`procesamiento/`/`grafo/`).
2. Script principal (p.ej. `herramientas/costes/desglose_glue.py`):
   - Recorre los jobs de Glue reales (`aws glue get-jobs`/`get-job-runs`,
     vía `boto3`), suma DPU-segundos por job y por dataset, aplica un
     precio por DPU-hora configurable (variable de entorno o argumento,
     con `0.44` USD como valor por defecto documentado como aproximado, no
     oficial).
   - Señala explícitamente los jobs con ejecuciones en `TIMEOUT`/`FAILED`
     recientes (como las que motivaron esta tarea) — coste sin resultado
     útil es la señal más urgente, no solo el total.
   - Calcula una tendencia simple (coste de las últimas 5 ejecuciones vs
     las primeras 5 de cada job, o regresión lineal simple sobre
     DPU-segundos por ejecución en el tiempo — elige el método más simple
     que sea razonable, no hace falta nada sofisticado) y proyecta
     coste/día y coste/mes si esa tendencia continúa.
   - Salida legible en terminal (tabla), y opcionalmente un JSON para
     consumo programático.
3. Tests con datos de `get-job-runs` mockeados (sin llamadas reales a AWS
   en los tests) — sigue el mismo criterio que `grafo/tests/`.
4. `herramientas/costes/README.md`: cómo ejecutarlo, qué mide y qué no
   (dejar explícito que es una estimación por uso, no el dato oficial de
   Cost Explorer/Billing, y por qué: el bloqueo de permisos documentado
   arriba).

## Restricciones

- NO intentes dar de alta permisos de Cost Explorer (`ce:*`) — ya se
  evaluó y se descartó por esta vez, ver Contexto. Si crees que de verdad
  hace falta, documéntalo como recomendación en el README en vez de
  intentarlo.
- NO ejecutes ninguna acción con efectos reales sobre la infraestructura
  (esta tarea es de solo lectura/reporting).
- Si añadir Lambda/Athena/S3 al desglose resulta significativamente más
  complejo que Glue (p.ej. por no tener un equivalente directo a
  `get-job-runs`), no fuerces cubrirlos todos — cubre bien Glue (la causa
  del problema que motivó esta tarea) y documenta el resto como trabajo
  futuro.

## Criterios de aceptación

- El script produce un desglose real (ejecutado contra la cuenta real,
  no solo con datos de prueba) coherente con los números ya conocidos de
  esta sesión (~70 USD acumulados en Glue a fecha de esta tarea).
- La proyección de coste/mes tiene sus supuestos documentados y es
  legible sin necesitar contexto adicional.
- Tests en verde sin llamadas reales a AWS.
- `herramientas/costes/README.md` documenta el uso y las limitaciones.
