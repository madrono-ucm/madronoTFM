---
id: 72
slug: arreglo-lectura-incremental-glue
title: 'URGENTE: lectura incremental para trafico y bicimad (los dos jobs en timeout
  activo)'
status: in_review
force: false
allow_infra_apply: true
branch: task/072-arreglo-lectura-incremental-glue
pr_number: 119
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/119
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-22T09:00:00+00:00'
updated_at: '2026-08-22T16:44:37.808679+00:00'
started_at: '2026-08-22T16:20:23.406965+00:00'
submitted_at: '2026-08-22T16:44:37.808657+00:00'
merged_at: null
---

## Contexto

**Bug de coste real y activo — máxima prioridad, por delante de cualquier
otra tarea en cola.** Un primer intento de esta tarea (alcance: los 14
datasets, 28 ficheros) agotó el presupuesto ($6, ~10.3M tokens, ~18 min)
sin comitear nada. **Se reduce el alcance a los dos datasets más urgentes**
— el resto (4 datasets más del grupo horario, 8 del grupo diario) son las
tareas 073/074, creadas aparte para no repetir el mismo fallo.

**Verificado de nuevo justo antes de reescribir esta tarea (con `aws glue
get-job-runs`)**: `trafico-silver-to-gold` y `bicimad-silver-to-gold`
llevan **muchas horas seguidas terminando en `TIMEOUT`** (se cortan a los
30 min configurados, sin completar ni actualizar Gold), facturando la hora
completa de DPU en cada intento fallido. Sus jobs Bronze→Silver hermanos
siguen completando (`SUCCEEDED`) pero cada vez más lento
(`trafico-bronze-to-silver` ~0.49 DPU-h/run, `bicimad-bronze-to-silver`
~0.26 DPU-h/run, ambos subiendo). Coste acumulado hasta ahora en estos 4
jobs: ~99 DPU-horas (~44 USD estimados) de un total de ~159 DPU-horas en
los 28 jobs.

**Causa raíz, confirmada leyendo el código**:
`procesamiento/silver_gold/trafico/glue_bronze_to_silver.py` y
`.../bicimad/glue_bronze_to_silver.py` hacen
`spark.read.option("multiLine", True).json(args["bronze_path"])`, y los
`glue_silver_to_gold.py` correspondientes hacen
`spark.read.parquet(args["silver_path"])`, pasando **la ruta raíz del
dataset completo**, sin ningún filtro de fecha/hora — cada ejecución
reprocesa todo el histórico acumulado desde el principio, no solo los
datos nuevos.

**Mitigación ya aplicada fuera de esta tarea**: los 6 triggers `SCHEDULED`
del grupo horario (incluidos `trafico`/`bicimad`) están desactivados
(`aws glue stop-trigger`, directamente vía API, sin pasar por Terraform —
el estado de Terraform sigue marcándolos `ACTIVATED`, cuidado con un
`apply` sin `-target`). **Confirma al empezar que siguen desactivados** —
si algo los hubiera reactivado entretanto, algo iría muy mal y hay que
investigarlo antes de seguir.

**`force: false` deliberado**: cambia cómo se procesan datos de producción
reales — reviso antes de fusionar.

## Objetivo

Arreglar la lectura de `trafico` y `bicimad` (Bronze→Silver y
Silver→Gold, 4 ficheros) para que cada ejecución procese solo los datos
nuevos, reactivar sus 2 triggers `SCHEDULED` una vez verificado, y
confirmar con una ejecución real que el coste por ejecución vuelve a ser
proporcional.

## Alcance concreto

1. En los 4 ficheros (`procesamiento/silver_gold/{trafico,bicimad}/
   glue_{bronze_to_silver,silver_to_gold}.py`): filtra la lectura a la
   partición que toca procesar en vez de la ruta raíz.
   - **Bronze→Silver**: los objetos ya están particionados por
     `fecha=.../hora=.../` en S3 (`ingesta/capturas/bronze.py`). Pasa como
     `bronze_path` solo la partición de la hora que toca procesar
     (calculada a partir de `processed_at`/hora de disparo), no la raíz.
   - **Silver→Gold**: mismo criterio, filtra `silver_path` a la partición
     `fecha`/`hora` que corresponde a lo que acaba de escribir el
     Bronze→Silver anterior.
2. Actualiza los tests de `procesamiento/tests/` que cubran estos 4
   ficheros si la lógica cambiada es testeable sin `pyspark` (el cálculo de
   qué partición/ruta tocar sí lo es — aíslalo en una función pura si no lo
   está ya).
3. `terraform apply` acotado con `-target` a los 4 `aws_glue_job` de estos
   dos datasets únicamente (mismo patrón que la tarea 065/068 — no toques
   Kafka ni nada no relacionado, ni el resto de datasets).
4. Reactiva los 2 triggers `SCHEDULED` (`trafico`, `bicimad`) **solo
   después de** verificar el arreglo.
5. Fuerza una ejecución real de Bronze→Silver y Silver→Gold de ambos
   datasets y confirma que la duración/DPU-segundos de esta ejecución es
   del orden de un job "sano" (minutos, no decenas de DPU-hora ni
   `TIMEOUT`).
6. Documenta en `doc/072-arreglo-lectura-incremental-glue.md` el
   diagnóstico, el arreglo aplicado, el coste real acumulado en estos 4
   jobs hasta ahora, y la verificación de que el coste por ejecución vuelve
   a ser proporcional.

## Restricciones

- Alcance: solo `trafico`/`bicimad` (4 ficheros, 2 triggers) — el resto es
  las tareas 073/074, no las adelantes aunque parezca poco esfuerzo extra.
- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO reactives los triggers hasta haber verificado el arreglo.
- NO toques los otros 12 triggers (4 horarios + 8 diarios) ni su código.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/072-...md` — dado el coste ya incurrido, un resultado a medias
  documentado es preferible a un intento perdido sin comitear nada.

## Criterios de aceptación

- `trafico` y `bicimad` (Bronze→Silver y Silver→Gold) procesan solo datos
  nuevos por ejecución, verificado con una ejecución real sin `TIMEOUT` y
  con coste proporcional.
- Sus 2 triggers `SCHEDULED` están reactivados tras verificar el arreglo.
- `doc/072-arreglo-lectura-incremental-glue.md` documenta el diagnóstico,
  el coste real incurrido, y la verificación.
- Hay un commit real con estos cambios.
