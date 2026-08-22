# 073 — Lanzar la reconstrucción deduplicada de bicimad (completada fuera de la cola de tareas)

## Qué pasó realmente

Esta tarea (en sus distintas versiones: primero como parte de una limpieza
conjunta trafico+bicimad, luego dividida en "lanzar" + "verificar" tras
varios fallos) se intentó **seis veces** de forma autónoma vía
`madrono-agent`, y las seis terminó **sin comitear nada**, pese a que cada
intento dejaba progreso real en AWS:

| Intento | Qué tocó en AWS | Resultado |
|---|---|---|
| 1-2 (versión conjunta trafico+bicimad) | Borró partes de Silver de `trafico` sin reconstruir del todo | `trafico` quedó con huecos de fecha |
| 3 | Reconstruyó Silver de `trafico` correctamente (esto sí se conservó y se verificó bueno) | `trafico` Silver arreglado |
| 4 | Reconstruyó Gold de `trafico`; tocó `bicimad` pero solo compactó ficheros sin deduplicar de verdad | `trafico` completo; `bicimad` seguía con `n=6752` duplicados |
| 5 (versión "lanzar", dividida) | No llegó a escribir nada | Sin cambios |
| 6 (versión "lanzar") | Escribió `glue_backfill_dedup.py`, aplicó el `aws_glue_job` nuevo en AWS real, borró parte de Silver de `bicimad` | Job creado y aplicado, pero nunca lanzado; Silver de `bicimad` quedó reducido a 3 fechas (20-22), sin deduplicar |

En ningún caso el fallo fue por agotar el presupuesto de $6 (serían errores
`error_max_budget_usd` explícitos) — el patrón (`claude finalizó sin crear
ningún commit`, sesión terminada limpiamente) apunta a que la combinación de
borrar S3 + esperar un job de Glue de varios minutos + verificar con Athena +
documentar, todo en una sola sesión síncrona, agotaba los turnos disponibles
antes de llegar al `git commit` final.

## Qué se hizo para desbloquearlo

Tras el sexto fallo, en vez de reintentar una séptima vez con el mismo
patrón, se recuperó directamente el trabajo ya válido que había quedado
aplicado en AWS pero nunca comiteado:

1. Se descargó el script real ya desplegado en S3
   (`s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/
   bicimad_backfill_dedup-*.py`) y se revisó: reutiliza correctamente la
   normalización de `glue_bronze_to_silver.py`, aplica
   `dropDuplicates(["station_id", "measured_at"])` antes de escribir, fija
   el timezone de sesión de Spark a `Europe/Madrid` (mismo arreglo que la
   tarea 072), y escribe con `mode("overwrite")`.
2. Se comiteó ese script tal cual en
   `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, y el bloque
   `aws_glue_job.bicimad_silver_backfill_dedup` correspondiente en
   `infra/terraform/glue.tf` (con `timeout = 90` minutos, más alto que el
   resto de jobs porque este lee todo el histórico de Bronze de una vez) —
   verificado con `terraform plan -target=...` que da **"No changes"**
   contra la infraestructura real tras ajustar el timeout, confirmando que
   el código comiteado coincide exactamente con lo aplicado.
3. **No hizo falta borrar manualmente el prefijo de Silver antes de
   lanzar**, pese a lo que decía el docstring original del script: por
   defecto, `DataFrame.write.mode("overwrite")` sobre una escritura
   particionada en Spark sustituye **todo** el directorio de destino (modo
   estático, no el modo dinámico de sobrescribir solo particiones nuevas),
   así que el propio job limpia lo que hubiera antes.
4. Se lanzó manualmente: `aws glue start-job-run --job-name
   madrono-tfm-dev-bicimad-silver-backfill-dedup` →
   `JobRunId: jr_6f09053f6eea77a852b5ff8e6db22fb984a459a4238648cf66204f1e0d8f5731`.

## Estado al cerrar esta tarea

El job **sigue en `RUNNING`** en el momento de este commit (lanzado
2026-08-22T23:07:17Z). La tarea 074 recoge este `JobRunId`, espera a que
termine, verifica con Athena que ya no hay duplicados, y completa Gold de
`bicimad` con el mismo enfoque (un job de backfill de un solo uso, no el
pipeline incremental).

## Relevante para tareas futuras

- El patrón "job de Glue de un solo uso, fuera del pipeline incremental,
  para una reconstrucción completa histórica" (este script) es reutilizable
  si algún otro dataset necesitara lo mismo — no debería hacer falta de
  nuevo si las tareas 075/076 (grupo horario/diario) confirman que solo
  `trafico`/`bicimad` tenían duplicación real (los datasets de menor
  volumen no llegaron a acumular tantas ejecuciones históricas antes del
  arreglo de la tarea 072).
- Cuando una tarea combine "lanzar algo que tarda minutos" con "verificar y
  documentar", dividirla en lanzar (sin esperar) + verificar (en otra
  sesión) es el patrón que ha funcionado en esta serie — puede ser útil
  documentarlo como convención en `tasks/README.md` si se repite.
