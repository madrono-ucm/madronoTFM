---
id: 77
slug: limpieza-duplicados-grupo-diario-resto
title: "Lanzar y verificar el backfill deduplicado de aforos_peatones_bicicletas, ruido y cams_calidad_aire"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-23T15:40:00+00:00"
updated_at: "2026-08-23T15:40:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Última pieza pendiente de la serie de limpieza de duplicados (tareas
072-077, ver `doc/077-limpieza-duplicados-grupo-diario.md` para el
diagnóstico completo). Confirmado con datos reales que `ruido` (`n=6`),
`cams_calidad_aire` (`n=10`) y `aforos_peatones_bicicletas` (`n=6`) tienen
duplicación real — misma escala que `agenda_eventos`/`bluesky_menciones`,
ya limpiados en la tarea 077 anterior.

**Todo el código y la infraestructura ya están listos y aplicados en AWS
real** — esta tarea es solo lanzar, esperar y verificar, no escribir nada
nuevo:

- `procesamiento/silver_gold/{aforos_peatones_bicicletas,ruido,cams_calidad_aire}/glue_backfill_dedup.py`
  + `glue_backfill_dedup_gold.py` ya existen y están comiteados.
- Los 6 `aws_glue_job` correspondientes (Silver + Gold × 3 datasets:
  `madrono-tfm-dev-<dataset>-silver-backfill-dedup`/`-gold-backfill-dedup`)
  ya están aplicados en AWS — **no hace falta `terraform apply`** salvo que
  compruebes con `terraform plan` que hay drift (no debería haberlo).
- Claves de deduplicación ya usadas por los scripts (no las reabras):
  `aforos_peatones_bicicletas`: `(station_id, mode, measured_at)`;
  `ruido`: `(station_id, period, measured_date)`; `cams_calidad_aire`:
  `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)`.

**Importante — `aforos_peatones_bicicletas` no es consultable con Athena**:
su tabla tiene `partition projection` configurado con
`projection.fecha.range = "2026-08-01,NOW+1DAY"`, pero sus datos reales son
de 2024 (fuera de rango) — cualquier `SELECT` devuelve 0 filas en silencio,
sin error. Verifica este dataset descargando los objetos parquet reales y
agregando con `pyarrow` directamente en Python (igual que hizo la tarea
077 anterior para diagnosticarlo), no con Athena.

**`force: false` deliberado**: borra y reescribe datos de producción
reales.

## Objetivo

Para cada uno de los 3 datasets: vaciar Silver/Gold, lanzar su backfill
deduplicado ya aplicado, esperar a que termine, y verificar que ya no hay
duplicados.

## Alcance concreto

Para cada uno de `aforos_peatones_bicicletas`, `ruido`, `cams_calidad_aire`:

1. `aws s3 rm --recursive` sobre el prefijo Silver del dataset, luego sobre
   el prefijo Gold (revisa el nombre exacto de la tabla Gold en `glue.tf`
   si no coincide literalmente).
2. `aws glue start-job-run --job-name madrono-tfm-dev-<dataset>-silver-backfill-dedup`,
   espera con sondeos razonables (cada 30-60s) hasta que termine.
3. Verifica Silver sin duplicados: para `ruido`/`cams_calidad_aire`, consulta
   Athena sobre la clave natural correspondiente (debe dar `n=1`); para
   `aforos_peatones_bicicletas`, descarga y agrega con `pyarrow` (ver nota
   de Contexto).
4. Solo si el paso 3 confirma que Silver está limpio:
   `aws glue start-job-run --job-name madrono-tfm-dev-<dataset>-gold-backfill-dedup`,
   espera, y verifica Gold (fechas sin huecos respecto a Bronze, agregación
   coherente).
5. **Completa cada dataset entero (Silver + Gold + verificado) antes de
   empezar el siguiente** — si el presupuesto no llega para los 3,
   prioriza terminar los que puedas por completo, documentando
   explícitamente cuál quedó pendiente si no te da tiempo a los 3, en vez
   de dejar varios a medias.
6. Documenta en `doc/077-limpieza-duplicados-grupo-diario-resto.md` el
   resultado de cada dataset con números reales (antes/después).

## Restricciones

- Alcance: solo estos 3 datasets — el resto de la serie ya está cerrado.
- NO toques Bronze.
- NO ejecutes `terraform apply` salvo que detectes drift real (no
  esperado) — la infraestructura ya está aplicada.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/077-...md`, aunque no completes los 3 — documenta exactamente qué
  se hizo y qué quedó pendiente.

## Criterios de aceptación

- Los 3 datasets (o los que el presupuesto permita, documentado
  explícitamente) tienen Silver y Gold reconstruidos sin duplicados,
  verificado con números reales.
- `doc/077-limpieza-duplicados-grupo-diario-resto.md` documenta el
  resultado.
- Hay un commit real con estos cambios.
