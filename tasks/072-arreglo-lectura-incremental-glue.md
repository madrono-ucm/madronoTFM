---
id: 72
slug: arreglo-lectura-incremental-glue
title: 'URGENTE: arreglar la lectura incremental de Bronze→Silver→Gold (coste de Glue
  descontrolado)'
status: blocked
force: false
allow_infra_apply: true
branch: task/072-arreglo-lectura-incremental-glue
pr_number: null
pr_url: null
attempts: 3
next_retry_at: '2026-08-21T21:49:28.596724+00:00'
last_error: You've hit your session limit · resets 1:10am (UTC)
created_at: '2026-08-22T09:00:00+00:00'
updated_at: '2026-08-21T21:30:51.222197+00:00'
started_at: '2026-08-21T21:01:04.156415+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Bug de coste real, activo, y empeorando cada hora — máxima prioridad,
por delante de cualquier otra tarea en cola.** El usuario reportó una
factura de Glue de 39,71 USD y se ha confirmado la causa fuera de esta
tarea (verificado con `aws glue get-job-runs` sobre los 28 jobs):

| Job | Runs (desde que arrancó producción) | DPU-horas acumuladas |
|---|---|---|
| `bicimad-silver-to-gold` | 45 | **37.85** |
| `trafico-silver-to-gold` | 44 | **29.75** |
| `trafico-bronze-to-silver` | 50 | **20.04** |
| `bicimad-bronze-to-silver` | 48 | **10.79** |
| (resto, p.ej. `aparcamientos-silver-to-gold`) | 48 | 1.61 (normal) |

**Causa raíz, confirmada leyendo el código, no solo inferida**:
`procesamiento/silver_gold/*/glue_bronze_to_silver.py` hace
`spark.read.option("multiLine", True).json(args["bronze_path"])` y
`glue_silver_to_gold.py` hace `spark.read.parquet(args["silver_path"])`
pasando **la ruta raíz del dataset completo**, sin ningún filtro de
fecha/hora — cada ejecución reprocesa **todo el histórico acumulado desde
el principio**, no solo los datos nuevos desde la última vez. Como Bronze
crece sin parar (ingesta cada 5-15 min desde hace días), cada ejecución es
más cara que la anterior — no es un pico puntual, es una trayectoria de
coste creciente sin límite. Afecta a los 14 datasets por igual en diseño;
hoy es más visible en `trafico`/`bicimad` porque son los de mayor volumen,
pero el resto llegará al mismo punto con el tiempo si no se arregla.

**Mitigación ya aplicada fuera de esta tarea, antes de crearla**: se han
desactivado (`aws glue stop-trigger`) los 6 triggers `SCHEDULED` del grupo
horario (`trafico`, `transporte_publico_emt`, `bicimad`, `aparcamientos`,
`calidad_aire`, `meteorologia`) directamente vía API, **sin pasar por
Terraform** — el estado de Terraform sigue marcándolos como `ACTIVATED`,
así que un `terraform apply` sin cuidado los reactivaría. Los 8 triggers
del grupo diario siguen activos (su coste actual es bajo, cadencia mucho
menor), pero comparten el mismo bug y deberían arreglarse también.

**`force: false` deliberado**: cambia cómo se procesan datos de producción
reales — reviso antes de fusionar. **`allow_infra_apply: true`**: permiso
para relanzar jobs de verificación y, si hiciera falta, ajustar
`aws_glue_job`/triggers.

## Objetivo

Arreglar la lectura para que cada ejecución procese solo los datos nuevos
desde la última ejecución exitosa (no el histórico completo), reactivar los
6 triggers desactivados con el código ya corregido, y confirmar con una
ejecución real que el tiempo/coste por run vuelve a ser proporcional al
volumen de una hora, no al histórico acumulado.

## Alcance concreto

1. Decide e implementa el filtro incremental. Opciones a evaluar (elige la
   más simple que funcione, documenta por qué):
   - **Bronze→Silver**: los objetos ya están particionados por
     `fecha=.../hora=.../` en S3 (ver `ingesta/capturas/bronze.py`). Pasa
     como `bronze_path` solo la partición de la hora que toca procesar
     (calculada a partir de `processed_at`/hora de disparo), no la raíz del
     dataset — igual que ya hace bien, por ejemplo, cómo está particionado
     el propio bucket. Para los datasets de cadencia diaria, la partición
     equivalente por fecha.
   - **Silver→Gold**: mismo criterio, filtra `silver_path` por la partición
     `fecha`/`hora` (o `fecha`, según el dataset) que corresponde a lo que
     acaba de escribir el Bronze→Silver anterior, no todo Silver.
   - Si algún dataset agrega sobre una ventana más ancha por diseño (p.ej.
     `ruido` con su media móvil de 7 días, tarea 053), decide el filtro
     mínimo que siga siendo correcto para ese caso concreto (leer solo los
     últimos N días en vez de reprocesar todo el histórico), no lo dejes
     igual de roto ni sobre-optimices con un filtro que rompa la lógica ya
     testada.
2. Aplica este arreglo a los 28 `glue_bronze_to_silver.py`/
   `glue_silver_to_gold.py` (14 datasets × 2 etapas) — es un cambio
   sistemático, no distinto por dataset salvo el caso de ventana ancha
   mencionado arriba.
3. Actualiza los tests de `procesamiento/tests/` si la lógica cambiada es
   testeable sin `pyspark` (el cálculo de qué partición/ruta tocar sí lo
   es, aíslalo en una función pura si no lo está ya).
4. `terraform apply` acotado con `-target` a los 28 `aws_glue_job` (mismo
   patrón que la tarea 065/068 — no toques Kafka ni nada no relacionado)
   para desplegar el código corregido.
5. Reactiva los 6 triggers `SCHEDULED` desactivados
   (`aws glue start-trigger`) **solo después de** verificar el arreglo.
6. Verifica con al menos `trafico` y `bicimad` (los más afectados): fuerza
   una ejecución real de Bronze→Silver y Silver→Gold y confirma que la
   duración/DPU-segundos de esta ejecución es del orden de las ejecuciones
   "sanas" de la tabla de arriba (minutos, no decenas de DPU-hora), no del
   orden de las últimas ejecuciones rotas.
7. Documenta en `doc/072-arreglo-lectura-incremental-glue.md` el
   diagnóstico completo, el arreglo aplicado, el coste real acumulado hasta
   ahora (tabla de arriba) y la verificación de que el coste por ejecución
   vuelve a ser proporcional.

## Restricciones

- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO reactives los 6 triggers hasta haber verificado el arreglo con al
  menos `trafico`/`bicimad`.
- NO toques el grupo diario (8 triggers) más allá de aplicarles el mismo
  arreglo de código — siguen activos, no los desactives ni los alteres de
  otra forma.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/072-...md` — dado el coste ya incurrido, un resultado a medias
  documentado es preferible a un intento perdido sin comitear nada.

## Criterios de aceptación

- Los 28 jobs procesan solo datos nuevos por ejecución, no el histórico
  completo, verificado con una ejecución real de `trafico`/`bicimad` con
  duración/coste proporcional.
- Los 6 triggers del grupo horario están reactivados tras verificar el
  arreglo.
- `doc/072-arreglo-lectura-incremental-glue.md` documenta el diagnóstico,
  el coste real incurrido, y la verificación.
- Hay un commit real con estos cambios.
