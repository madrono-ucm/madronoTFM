---
id: 74
slug: arreglo-lectura-incremental-glue-grupo-diario
title: "Lectura incremental para el grupo diario (8 datasets)"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-22T09:30:00+00:00"
updated_at: "2026-08-22T09:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Cierra la serie de las tareas 072/073 (mismo bug de lectura no incremental
en Bronze→Silver→Gold, ver `doc/072-...md` para el diagnóstico completo).
Esta tarea cubre el grupo diario: `ruido`, `aforos_peatones_bicicletas`,
`cartelera_cines_estrenos`, `agenda_eventos`, `bluesky_menciones`,
`aemet_prevision_avisos`, `cams_calidad_aire`, `afluencia_lugares` (16
ficheros, más los 2 pares de AEMET si se implementaron como jobs
independientes).

**Diferencia relevante frente a 072/073**: estos triggers **siguen
activos** (no se desactivaron, su coste actual es bajo por la cadencia
diaria) y `ruido` agrega sobre una ventana de 7 días (media móvil, tarea
053) — su filtro incremental no puede ser "solo el día de hoy" a secas, sin
romper esa media móvil. Decide el filtro correcto para ese caso concreto
(p.ej. leer los últimos 8 días de Silver en vez de todo el histórico, no
solo el día nuevo) y documenta por qué.

**`force: false` deliberado**: mismo criterio que 072/073.

## Objetivo

Aplicar el mismo arreglo de lectura incremental a los 8 datasets del grupo
diario, sin necesidad de reactivar ningún trigger (ya están activos) pero
verificando que la primera ejecución tras el arreglo no rompe nada.

## Alcance concreto

1. En los `glue_bronze_to_silver.py`/`glue_silver_to_gold.py` de los 8
   datasets: mismo patrón que 072/073 (partición `fecha` en vez de la ruta
   raíz), con la excepción de `ruido` (ver arriba, ventana de 7 días).
2. Actualiza los tests correspondientes si aplica.
3. `terraform apply` acotado con `-target` a los `aws_glue_job`
   correspondientes únicamente.
4. Espera al siguiente disparo real (o fuérzalo con `aws glue
   start-trigger`) de al menos 3 de los 8 datasets (incluido `ruido`, por
   su caso especial) y confirma que el resultado sigue siendo correcto
   (compara con el resultado que ya verificaron las tareas 062/063 antes de
   este arreglo) y con coste proporcional al volumen de un día, no al
   histórico completo.
5. Documenta en `doc/074-arreglo-lectura-incremental-glue-grupo-diario.md`.

## Restricciones

- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO desactives ningún trigger de este grupo — ya están activos y su coste
  actual es bajo, no hace falta pausarlos para aplicar este arreglo.
- **Antes de terminar, confirma que dejas un commit real.**

## Criterios de aceptación

- Los 8 datasets procesan solo datos nuevos por ejecución (con la excepción
  documentada de `ruido`), verificado con al menos 3 ejecuciones reales con
  resultado correcto y coste proporcional.
- `doc/074-...md` documenta el resultado, incluida la decisión tomada para
  `ruido`.
- Hay un commit real con estos cambios.
