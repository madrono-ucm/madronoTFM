---
id: 52
slug: verificar-silver-gold-completo
title: "Verificar Bronze→Silver→Gold de extremo a extremo para los 6 datasets"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-16T14:45:00+00:00"
updated_at: "2026-08-16T14:45:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

La tarea 051 arregló los dos bugs que bloqueaban los jobs de Glue de
Silver/Gold (`saveAsTextFile`/`DirectOutputCommitter` y `urllib3`/
`DEFAULT_CIPHERS`) y confirmó el arreglo con un único job de sanidad
(`trafico-bronze-to-silver`). Esta tarea completa la verificación real que
originalmente pedía la 051: una carga manual y puntual (sin schedule, sigue
sin querer producción continua todavía) para cada uno de los 6 datasets
(`trafico`, `transporte_publico_emt`, `bicimad`, `aparcamientos`,
`calidad_aire`, `meteorologia`), confirmando que Bronze→Silver→Gold produce
lo esperado en cada uno.

La infraestructura de Glue ya está aplicada (tarea 051) — esta tarea no
debería necesitar `terraform apply` salvo que encuentres algo que corregir.

**`force: false` deliberado**: quiero revisar los resultados reales antes de
decidir si programar esto en producción.

## Objetivo

Para cada uno de los 6 datasets, lanzar el job Bronze→Silver contra el lote
más reciente ya presente en Bronze, y el job Silver→Gold correspondiente, y
verificar que el resultado es el esperado.

## Alcance concreto

1. Para cada dataset: `aws glue start-job-run` del job Bronze→Silver,
   espera a que termine (`aws glue get-job-run`), y confirma en S3 que:
   - Silver contiene los registros esperados (número razonable, esquema
     correcto, ningún campo que debería haberse filtrado por la puerta de
     calidad).
   - El informe de Great Expectations se escribió correctamente (ahora vía
     `boto3`, arreglo de la tarea 051).
2. Lanza el job Silver→Gold correspondiente contra lo que se acaba de
   escribir en Silver, y confirma que Gold tiene la agregación esperada
   (compara a mano al menos un grupo de agregación contra los registros
   Silver de origen, por dataset).
3. Documenta en `doc/052-verificar-silver-gold-completo.md`, por dataset: si
   la carga completó sin error, cuánto tardó, cuántos registros
   entraron/salieron de cada etapa, y cualquier discrepancia entre lo
   esperado (según el código/tests de la tarea correspondiente) y lo real —
   incluye valores reales, no solo "funcionó".
4. Si algún dataset falla por un problema real de código (no de
   credenciales/permisos, y no uno de los dos bugs ya arreglados en la 051),
   documenta el error exacto — no intentes depurarlo ni arreglarlo aquí,
   sería una tarea de seguimiento (mismo criterio que la tarea 033 con
   Lambda).
5. Si el coste/tiempo de alguna ejecución de Glue resulta sorprendentemente
   alto, documéntalo explícitamente (es información relevante para decidir
   si programar esto en producción más adelante).

## Restricciones

- NO crees ningún trigger/schedule para estos jobs de Glue.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni ningún recurso de la fase de
  ingesta.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/052-verificar-silver-gold-completo.md`, aunque algún dataset siga
  fallando — un resultado parcial documentado es mucho más útil que terminar
  sin commitear nada (el motivo por el que la 051 tuvo que reintentarse dos
  veces). Si el volumen de trabajo resulta más grande de lo esperado,
  prioriza dejar documentados los datasets que sí completaste antes de
  quedarte sin presupuesto, en vez de arriesgarte a terminar sin nada
  comiteado.

## Criterios de aceptación

- Cada uno de los 6 datasets tiene al menos una ejecución real y verificada
  de Bronze→Silver→Gold, documentada con los resultados reales obtenidos (o,
  si alguno falla, el error exacto documentado).
- `doc/052-verificar-silver-gold-completo.md` documenta el resultado
  detallado, dataset por dataset.
- Hay un commit real con estos cambios.
