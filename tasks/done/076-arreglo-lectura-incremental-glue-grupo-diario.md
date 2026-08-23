---
id: 76
slug: arreglo-lectura-incremental-glue-grupo-diario
title: Lectura incremental para el grupo diario (8 datasets)
status: done
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 4
next_retry_at: null
last_error: null
created_at: '2026-08-22T09:30:00+00:00'
updated_at: '2026-08-23T14:15:00+00:00'
started_at: '2026-08-23T01:36:43.740792+00:00'
submitted_at: '2026-08-23T14:15:00+00:00'
merged_at: '2026-08-23T14:15:00+00:00'
---

## Contexto

Cierra la serie de las tareas 072-075 (mismo bug de lectura no
incremental en Bronze→Silver→Gold — **lee `doc/072-arreglo-lectura-
incremental-glue.md` completo antes de empezar**, documenta el diagnóstico
completo y dos bugs adicionales relevantes para esta tarea, ver abajo). Esta
tarea cubre el grupo diario: `ruido`, `aforos_peatones_bicicletas`,
`cartelera_cines_estrenos`, `agenda_eventos`, `bluesky_menciones`,
`aemet_prevision_avisos` (dos pares de jobs, previsión y avisos),
`cams_calidad_aire`, `afluencia_lugares`.

**Dato importante**: el código de lectura incremental de **Bronze→Silver ya
está desplegado para los 14 datasets**, incluidos estos 8 — fue un efecto
colateral necesario del `apply` de la tarea 072 (el artefacto de librería
compartido `procesamiento/` no se puede actualizar de forma parcial sin
romper a los jobs no tocados). Lo que falta para este grupo es: confirmar
que Silver→Gold también usa la lectura incremental (revísalo, puede que ya
esté en código desde la sesión que escribió `incremental.py` pero sin
desplegar), los dos bugs adicionales de abajo, y la limpieza de datos ya
duplicados.

**Dos bugs adicionales encontrados en la tarea 072, a confirmar/arreglar
también aquí**:
1. **`--extra-py-files` que puede faltar en los jobs Silver→Gold** de estos
   8 datasets (revísalo en `glue.tf`, sin él el import de `incremental.py`
   falla con `ModuleNotFoundError` en ejecución real, no lo detectan los
   tests unitarios).
2. **Timezone de sesión de Spark en UTC en vez de Europe/Madrid** al
   recalcular `fecha`/`hora` — desfase silencioso (Bronze→Silver escribe en
   la partición equivocada, Silver→Gold no la encuentra, `job.commit()` sin
   escribir nada, sin error). **No basta con que los tests unitarios pasen
   — verifícalo con una ejecución real.**

**Dato nuevo, posterior a como se escribió esta tarea la primera vez**:
Silver de `trafico`/`bicimad` tenía datos masivamente duplicados (hasta 88
copias del mismo registro) por reprocesar todo el histórico sin deduplicar
en cada ejecución — arreglado en las tareas 073/074. Estos 8 datasets, al
compartir exactamente el mismo patrón de código histórico, probablemente
tienen el mismo problema, aunque su volumen/nº de ejecuciones es menor
(cadencia diaria, no horaria) así que el factor de duplicación debería ser
mucho menor. **Confírmalo** (compara nº de objetos Bronze vs Silver de cada
dataset, o cuenta duplicados reales con una consulta Athena) y, si lo
confirmas, límpialo con el mismo procedimiento que documentaron las 073/074.

**Diferencia relevante frente al resto de esta serie**: estos triggers
**siguen activos** (nunca se desactivaron, su coste actual es bajo) y
`ruido` agrega sobre una ventana de 7 días (media móvil, tarea 053) — su
filtro incremental no puede ser "solo el día de hoy" a secas, sin romper esa
media móvil. Decide el filtro correcto para ese caso concreto (p.ej. leer
los últimos 8 días de Silver en vez de todo el histórico) y documenta por
qué.

**`force: false` deliberado**: mismo criterio que el resto de la serie.

## Objetivo

Confirmar/completar el arreglo de lectura incremental de Silver→Gold para
estos 8 datasets (incluidos los dos bugs adicionales), limpiar su
Silver/Gold si está duplicado, y verificar con ejecuciones reales sin
necesidad de reactivar ningún trigger (ya están activos).

## Alcance concreto

1. Confirma que `glue_silver_to_gold.py` de estos 8 (10 con los 2 pares de
   AEMET) ya usa `incremental.py` para acotar la lectura de Silver — si no,
   aplícalo con el mismo patrón que las tareas anteriores de esta serie, con la excepción de
   `ruido` (ventana de 7 días, ver arriba).
2. Añade `--extra-py-files` a los `aws_glue_job` Silver→Gold que lo tengan
   pendiente (punto 1 del Contexto).
3. Añade `spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")`
   donde falte (punto 2 del Contexto).
4. Actualiza los tests correspondientes si aplica.
5. `terraform apply` acotado con `-target` — mismo cuidado que la 075 con
   el artefacto compartido de `procesamiento/` (ver `doc/072-...md`).
6. Comprueba si Silver/Gold de estos 8 datasets está duplicado y, si lo
   está, límpialo (trunca y reconstruye desde Bronze).
7. Espera al siguiente disparo real (o fuérzalo con `aws glue
   start-trigger`) de al menos 3 de los 8 datasets (incluido `ruido`, por
   su caso especial) y confirma que Gold recibe datos reales correctos
   (compara con lo que ya verificaron las tareas 062/063), sin `TIMEOUT` ni
   no-ops silenciosos, con coste proporcional al volumen de un día.
8. Documenta en `doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`.

## Restricciones

- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO desactives ningún trigger de este grupo — ya están activos.
- **Antes de terminar, confirma que dejas un commit real.**

## Criterios de aceptación

- Los 8 datasets procesan solo datos nuevos por ejecución (con la excepción
  documentada de `ruido`), sin `--extra-py-files` faltante ni desfase de
  timezone, verificado con al menos 3 ejecuciones reales con Gold
  recibiendo datos reales correctos.
- Si Silver/Gold de estos 8 datasets estaba duplicado, está limpio y
  reconstruido.
- `doc/076-...md` documenta el resultado, incluida la decisión tomada para
  `ruido`.
- Hay un commit real con estos cambios.
