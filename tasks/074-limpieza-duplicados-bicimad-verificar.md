---
id: 74
slug: limpieza-duplicados-bicimad-verificar
title: Verificar la reconstrucción de bicimad y completar Gold
status: in_review
force: false
allow_infra_apply: true
branch: task/074-limpieza-duplicados-bicimad-verificar
pr_number: 120
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/120
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-22T21:40:00+00:00'
updated_at: '2026-08-22T23:33:06.653017+00:00'
started_at: '2026-08-22T23:12:32.149574+00:00'
submitted_at: '2026-08-22T23:33:06.652876+00:00'
merged_at: null
---

## Contexto

La tarea 073 falló seis veces de forma autónoma (ver
`doc/073-limpieza-duplicados-bicimad-lanzar.md` para el detalle completo) —
se completó recuperando directamente el trabajo ya aplicado en AWS y
comiteándolo fuera de la cola de tareas. El job de backfill
(`madrono-tfm-dev-bicimad-silver-backfill-dedup`) se lanzó manualmente con

```
JobRunId: jr_6f09053f6eea77a852b5ff8e6db22fb984a459a4238648cf66204f1e0d8f5731
```

y seguía en `RUNNING` en el momento de cerrar la 073 — **usa este
`JobRunId` directamente, no hace falta buscarlo en ningún otro sitio.**
Esta tarea comprueba que terminó bien, verifica que ya no hay duplicados, y
completa Gold con el mismo enfoque (un job de un solo uso, no el de
producción incremental).

`trafico` (Silver + Gold) ya está arreglado y verificado — no lo toques.

## Objetivo

Confirmar que la reconstrucción de Silver de `bicimad` terminó bien y sin
duplicados, y completar Gold de la misma forma.

## Alcance concreto

1. Comprueba el estado del `JobRunId` de arriba
   (`aws glue get-job-run --job-name madrono-tfm-dev-bicimad-silver-backfill-dedup
   --run-id jr_6f09053f6eea77a852b5ff8e6db22fb984a459a4238648cf66204f1e0d8f5731`).
   Si todavía está `RUNNING`, espera con sondeos
   razonables (p.ej. cada 30-60s) hasta un máximo razonable de tiempo — si
   sigue sin terminar tras una espera razonable, documenta el estado en el
   que lo dejas y para ahí, no fuerces nada.
2. Si terminó con éxito (`SUCCEEDED`): verifica con esta consulta Athena
   exacta que ya no hay duplicados:
   ```sql
   SELECT station_id, measured_at, COUNT(*) AS n
   FROM bicimad GROUP BY station_id, measured_at ORDER BY n DESC LIMIT 5
   ```
   El resultado de `n` en la primera fila debe ser `1`. Verifica también
   que las particiones de fecha cubren el mismo rango que Bronze (2.249
   objetos, sin huecos).
3. Si terminó con error, o si la verificación no da `n=1`: documenta el
   error/resultado exacto — no reintentes más de una vez sin entender la
   causa, sería una tarea de seguimiento.
4. Solo si el paso 2 confirma que Silver está limpio: escribe
   `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py` (mismo
   patrón que el de Silver de la tarea 073, sin necesidad de
   `dropDuplicates` — el Silver de origen ya está limpio, es una
   agregación normal como la de producción pero sobre todo el histórico de
   una vez), el `aws_glue_job` correspondiente en `glue.tf`
   (`terraform apply` acotado con `-target`), borra
   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/` y
   lánzalo — esta vez sí puedes esperar a que termine (la agregación sobre
   Silver ya reducido debería ser rápida, minutos, no como el paso 1).
5. Verifica Gold con `aws s3 ls` (fechas sin huecos) y una consulta Athena
   de agregación básica.
6. Documenta en `doc/074-limpieza-duplicados-bicimad-verificar.md` el
   resultado completo de toda la serie (073+074): estado final de
   `bicimad` Silver y Gold, con números reales.

## Restricciones

- NO toques `trafico` — ya está cerrado.
- NO toques Bronze.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  ni sus triggers ni los jobs de producción existentes.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/074-...md`, aunque el job de Silver siga corriendo o haya fallado —
  documenta el estado exacto en el que lo dejas.

## Criterios de aceptación

- Silver de `bicimad` confirmado sin duplicados (`n=1`) y sin huecos de
  fecha, o el documento explica exactamente por qué no se pudo confirmar.
- Si Silver está limpio, Gold de `bicimad` reconstruido y verificado.
- `doc/074-limpieza-duplicados-bicimad-verificar.md` documenta el
  resultado final de toda la serie con números reales.
- Hay un commit real con estos cambios.
