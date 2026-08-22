---
id: 73
slug: limpieza-duplicados-trafico-bicimad
title: 'URGENTE: limpiar los datos duplicados de trafico/bicimad en Silver/Gold'
status: failed
force: false
allow_infra_apply: true
branch: task/073-limpieza-duplicados-trafico-bicimad
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: claude finalizó sin crear ningún commit
created_at: '2026-08-22T18:00:00+00:00'
updated_at: '2026-08-22T20:11:25.775264+00:00'
started_at: '2026-08-22T19:57:04.373252+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Dos intentos previos de esta tarea han terminado sin comitear nada.**
Verificado manualmente fuera de la sesión de `claude` (con `aws s3 ls` y
consultas Athena reales) el estado real dejado por el segundo intento —
**progreso real, no lo repitas**:

- **Silver de `trafico`: YA ARREGLADO Y VERIFICADO.** `fecha=2026-08-15` a
  `2026-08-22` completas (sin huecos), 6.768 objetos, y una consulta Athena
  real (`SELECT point_id, measured_at, COUNT(*) ... GROUP BY ... ORDER BY n
  DESC`) devuelve `n=1` en las filas con más duplicados — **sin
  duplicados**. **No lo reconstruyas otra vez.**
- **Gold de `trafico`: VACÍO** (0 objetos en
  `s3://madrono-tfm-dev-gold-222234418587/trafico_por_punto_hora/`) — el
  intento anterior lo borró y nunca llegó a reconstruirlo antes de quedarse
  sin presupuesto. **Esto es lo primero que hay que terminar.**
- **`bicimad`: sin tocar, sigue exactamente como al principio** — Silver con
  117.808 objetos, masivamente duplicado (mismo tipo de problema que tenía
  `trafico`), Gold con datos calculados sobre ese Silver duplicado. Nota
  aparte, no bloqueante para esta tarea: Silver/Gold de `bicimad` tienen una
  partición `fecha=1970-01-01`/`date=1970-01-01` — probablemente algún
  registro con `measured_at` nulo o no parseable cayendo al epoch Unix por
  defecto; investígalo solo si es trivial hacerlo de paso, si no,
  documéntalo para una tarea de seguimiento aparte, no es el objetivo de
  esta tarea.

Bronze no está afectado en ningún caso (nunca se sobrescribe).

**`force: false` deliberado**: borra y reescribe datos de producción reales.

## Objetivo

Terminar lo que falta: reconstruir Gold de `trafico` desde el Silver ya
limpio, y arreglar `bicimad` (Silver + Gold) igual que ya se hizo con
`trafico`.

## Alcance concreto

1. **Primero, `trafico` Gold** (lo más rápido de cerrar, y lo que dejó a
   medias el intento anterior): reconstruye
   `gold.trafico_por_punto_hora` desde el Silver ya limpio y verificado
   (arriba) — no hace falta deduplicar aquí, Silver ya está limpio, solo
   agregar. Verifica con `aws s3 ls` que hay datos para las fechas
   correspondientes y con una consulta Athena que el resultado tiene
   sentido (compara con la forma de salida que ya validaron las tareas
   041/051/052).
2. **Después, `bicimad` completo** (Silver + Gold, desde cero, igual que se
   hizo con `trafico`): borra con `aws s3 rm --recursive` todo el
   contenido de `s3://madrono-tfm-dev-silver-222234418587/bicimad/` y
   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`, y
   reconstruye desde Bronze con `dropDuplicates(["station_id",
   "measured_at"])` antes de escribir Silver, luego agrega a Gold desde ese
   Silver limpio.
3. **No des la tarea por completa hasta que Gold de `trafico` Y Silver+Gold
   de `bicimad` estén los tres terminados** — si el presupuesto no llega
   para bicimad completo, termina al menos Gold de `trafico` (ya
   verificado, es rápido) y dedica el resto a bicimad Silver (más
   importante que Gold, ya que Gold depende de él) antes que dejar los tres
   a medias otra vez.
4. Verifica `bicimad` con la misma consulta Athena tipo
   (`station_id`+`measured_at`, debe dar `n=1`) y confirma fechas sin
   huecos respecto a Bronze.
5. Documenta en `doc/073-limpieza-duplicados-trafico-bicimad.md`: el estado
   real dejado por los dos intentos anteriores (resumen de este contexto),
   qué completaste en esta sesión, y la verificación con números reales de
   cada pieza que termines.

## Restricciones

- Alcance: solo `trafico`/`bicimad`.
- NO reconstruyas Silver de `trafico` — ya está limpio y verificado, tocarlo
  otra vez sería trabajo perdido y coste innecesario.
- NO toques Bronze.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  ni sus triggers.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/073-...md`, documentando exactamente qué completaste — dos intentos
  seguidos sin comitear nada ya han costado demasiado tiempo de cola; si
  solo te da tiempo a terminar Gold de `trafico`, comitea eso documentado
  y para ahí, no sigas sin dejar rastro.

## Criterios de aceptación

- Gold de `trafico` reconstruido y verificado.
- Silver y Gold de `bicimad` sin duplicados (verificado con Athena) y sin
  huecos de fecha respecto a Bronze, o el documento explica exactamente qué
  quedó pendiente si no diera tiempo.
- `doc/073-limpieza-duplicados-trafico-bicimad.md` documenta todo lo
  anterior con números reales.
- Hay un commit real con estos cambios.
