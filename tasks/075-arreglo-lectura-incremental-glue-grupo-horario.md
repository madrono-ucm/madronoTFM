---
id: 75
slug: arreglo-lectura-incremental-glue-grupo-horario
title: Lectura incremental para el resto del grupo horario (EMT, aparcamientos, calidad
  del aire, meteorología)
status: in_progress
force: false
allow_infra_apply: true
branch: task/075-arreglo-lectura-incremental-glue-grupo-horario
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-22T09:30:00+00:00'
updated_at: '2026-08-23T00:39:07.026855+00:00'
started_at: '2026-08-23T00:39:07.026824+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa las tareas 072/073/074 (mismo bug, mismo motivo de división: un primer
intento cubriendo los 14 datasets a la vez agotó presupuesto sin comitear
nada). La 072 arregló el código de lectura de los dos datasets más urgentes
(`trafico`, `bicimad`, ya en `TIMEOUT` activo) y, como efecto colateral
necesario (el artefacto de librería compartido `procesamiento/` no se puede
actualizar de forma parcial sin romper a los demás), **ya desplegó el
código de lectura incremental de Bronze→Silver para los 14 datasets** —
pero **no** el de Silver→Gold de estos 4, ni sus triggers, ni la limpieza de
lo ya duplicado. Las 073/074 limpiaron los datos ya duplicados de `trafico`/
`bicimad`. Esta tarea cubre los 4 restantes del grupo horario:
`transporte_publico_emt`, `aparcamientos`, `calidad_aire`, `meteorologia`.

**Lee `doc/072-arreglo-lectura-incremental-glue.md` completo antes de
empezar** — documenta, además del arreglo de lectura, dos bugs adicionales
que muy probablemente afectan también a estos 4 datasets y que hay que
verificar/arreglar aquí:

1. **`--extra-py-files` que puede faltar en los jobs Silver→Gold**: los
   `glue_silver_to_gold.py` de estos 4 datasets importan
   `procesamiento.silver_gold.incremental` (ya escrito, sesión anterior a la
   072), pero sus `aws_glue_job` en `glue.tf` pueden no llevar el argumento
   `--extra-py-files` apuntando al artefacto compartido (a diferencia de los
   Bronze→Silver, que sí lo llevan desde la tarea 041) — sin él, el import
   falla con `ModuleNotFoundError` en ejecución real (no lo detectan los
   tests unitarios, que no ejecutan Spark). **Confírmalo en `glue.tf` para
   estos 4 datasets antes de desplegar, no lo des por hecho.**
2. **Timezone de sesión de Spark en UTC en vez de Europe/Madrid**: si algún
   `glue_bronze_to_silver.py`/`glue_silver_to_gold.py` de estos 4 recalcula
   `fecha`/`hora` con `date_format(to_timestamp(...), ...)` sin fijar antes
   `spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")`, sufre el
   mismo desfase silencioso que encontró la 072 (Bronze→Silver escribe en la
   partición de hora equivocada, Silver→Gold nunca la encuentra, hace
   `job.commit()` sin escribir nada en Gold — no es un error, es un no-op
   silencioso). **No basta con que los tests unitarios pasen en verde —
   verifícalo con una ejecución real**, igual que tuvo que hacer la 072.

**Además, dato nuevo desde que se escribió esta tarea la primera vez**:
Silver de estos 4 datasets probablemente tiene el mismo problema de
duplicación masiva que tenían `trafico`/`bicimad` (ver `doc/074-limpieza-duplicados-bicimad-verificar.md`) —
cada ejecución histórica reprocesaba y volvía a escribir todo el histórico
sin deduplicar. Confírmalo (compara nº de objetos en Bronze vs Silver de
cada dataset, o cuenta duplicados reales con una consulta Athena sobre
alguna clave conocida) y, si lo confirmas, aplica la misma limpieza que hizo
las 073/074 (truncar y reconstruir desde Bronze, ya con la lectura incremental
corregida).

Sus triggers `SCHEDULED` están desactivados desde antes de la tarea 072
(mitigación aplicada fuera de cola, vía `aws glue stop-trigger`, sin pasar
por Terraform). **Confirma al empezar que siguen desactivados.**

**`force: false` deliberado**: mismo criterio que el resto de la serie.

## Objetivo

Confirmar/completar el arreglo de lectura incremental de estos 4 datasets
(incluidos los dos bugs adicionales de arriba), limpiar su Silver/Gold si
está duplicado, reactivar sus 4 triggers tras verificar, y confirmar con una
ejecución real.

## Alcance concreto

1. Confirma si `procesamiento/silver_gold/{transporte_publico_emt,
   aparcamientos,calidad_aire,meteorologia}/glue_{bronze_to_silver,
   silver_to_gold}.py` (8 ficheros) ya usan `incremental.py` (probable, ver
   Contexto) — si no, aplica el mismo patrón que las tareas anteriores de esta serie.
2. Añade `--extra-py-files` a los `aws_glue_job` Silver→Gold de estos 4 en
   `glue.tf` si falta (punto 1 del Contexto).
3. Añade `spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")` a
   los ficheros que recalculen `fecha`/`hora` en Spark si falta (punto 2 del
   Contexto).
4. Actualiza los tests correspondientes si aplica.
5. `terraform apply` acotado con `-target` — **cuidado con el artefacto
   compartido de `procesamiento/`** (ver `doc/072-...md`, sección
   "Desplegado en AWS": aplicar solo un subconjunto de jobs con `-target`
   puede forzar el reemplazo del zip compartido y romper el
   `--extra-py-files` ya desplegado de jobs que no tocas si no incluyes
   también sus recursos en el mismo `apply` — decide el conjunto de
   `-target` con ese riesgo en mente, no asumas que basta con los 8 de
   estos 4 datasets).
6. Comprueba si Silver/Gold de estos 4 datasets está duplicado (ver
   Contexto) y, si lo está, límpialo (trunca y reconstruye desde Bronze).
7. Reactiva sus 4 triggers `SCHEDULED` solo después de verificar todo lo
   anterior.
8. Fuerza una ejecución real de Bronze→Silver y Silver→Gold de al menos 2
   de los 4 datasets y confirma: coste/duración proporcional, sin
   `TIMEOUT`, Gold recibe datos reales de hoy (no un no-op silencioso).
9. Documenta en `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.

## Restricciones

- Alcance: solo estos 4 datasets (8 ficheros, 4 triggers) — el grupo diario
  es la tarea 076.
- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO reactives los triggers hasta haber verificado el arreglo end-to-end
  (Gold recibiendo datos reales, no solo "sin error").
- **Antes de terminar, confirma que dejas un commit real.**

## Criterios de aceptación

- Los 4 datasets procesan solo datos nuevos por ejecución, sin
  `--extra-py-files` faltante ni desfase de timezone, verificado con al
  menos 2 ejecuciones reales sin `TIMEOUT` y con Gold recibiendo datos
  reales.
- Si Silver/Gold de estos 4 datasets estaba duplicado, está limpio y
  reconstruido.
- Sus 4 triggers `SCHEDULED` están reactivados tras verificar.
- `doc/075-...md` documenta el resultado.
- Hay un commit real con estos cambios.
