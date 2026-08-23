---
id: 77
slug: limpieza-duplicados-grupo-diario
title: "Limpiar duplicados del grupo diario (agenda_eventos, bluesky_menciones y verificar el resto)"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-23T14:15:00+00:00"
updated_at: "2026-08-23T14:15:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

La tarea 076 arregló la lectura incremental del grupo diario (8 datasets),
pero **no llegó a limpiar los datos ya duplicados** por el mismo bug
histórico que afectó a `trafico`/`bicimad` (tareas 072-074) y al resto del
grupo horario (tarea 075) — ver `doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`
para el diagnóstico completo, no lo repitas aquí.

**Verificado con Athena real (ya hecho, no lo repitas)**:

| Dataset | Duplicación confirmada |
|---|---|
| `agenda_eventos` | **Sí** — `n=56` para `(title, start_datetime)` |
| `bluesky_menciones` | **Sí** — `n=19` para `post_hash` |
| `aforos_peatones_bicicletas` | No verificado — ratio Bronze/Silver alto (1→144) pero puede ser normal (un único CSV histórico de un año, fan-out legítimo a muchas particiones hora/estación, ver tarea 040) |
| `ruido` | No verificado, ratio bajo (5→19), probablemente sin problema |
| `cams_calidad_aire` | No verificado (17→136) |
| `cartelera_cines_estrenos`, `aemet_prevision_avisos`, `afluencia_lugares` | Sin datos en Silver (ya documentado como esperado en tareas anteriores) — no necesitan limpieza |

La escala de duplicación es mucho menor que la de `trafico`/`bicimad`
(decenas, no miles) — coherente con la cadencia diaria.

**`force: false` deliberado**: borra y reescribe datos de producción reales.

## Objetivo

Confirmar la duplicación real en los 3 datasets sin verificar
(`aforos_peatones_bicicletas`, `ruido`, `cams_calidad_aire`), y limpiar
(backfill deduplicado, mismo patrón que las tareas 073/074/075) los que
realmente lo necesiten — con certeza `agenda_eventos` y
`bluesky_menciones`.

## Alcance concreto

1. Para `aforos_peatones_bicicletas`, `ruido` y `cams_calidad_aire`: verifica
   con una consulta Athena real (mismo tipo que la tabla de arriba, sobre la
   clave natural de cada uno) si hay duplicación real antes de tocar nada.
2. Para cada dataset con duplicación confirmada (`agenda_eventos`,
   `bluesky_menciones`, y los que confirmes en el paso 1): escribe
   `glue_backfill_dedup.py`/`glue_backfill_dedup_gold.py` (mismo patrón que
   `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py` — revísalo
   como referencia directa, incluida la lección de la tarea 074: vacía el
   prefijo de destino a mano con `aws s3 rm --recursive` **antes** de
   lanzar el job, no confíes solo en `mode("overwrite")` a esta escala),
   aplica el `aws_glue_job` correspondiente en `glue.tf`
   (`terraform apply` acotado con `-target`), y lánzalo.
3. No des ningún dataset por completo hasta verificar con Athena tras el
   backfill (misma consulta que confirmó la duplicación, ahora debe dar
   `n=1`).
4. Si el presupuesto no llega para los 5 datasets potenciales, prioriza
   `agenda_eventos` y `bluesky_menciones` (duplicación ya confirmada) antes
   que los 3 por verificar — y termina cada uno por completo (Silver + Gold
   + verificado) antes de empezar el siguiente.
5. Documenta en `doc/077-limpieza-duplicados-grupo-diario.md` qué
   verificaste, qué limpiaste, y el resultado con números reales.

## Restricciones

- NO toques `trafico`/`bicimad` ni el resto del grupo horario — ya están
  cerrados.
- NO toques Bronze.
- NO toques `cartelera_cines_estrenos`, `aemet_prevision_avisos` ni
  `afluencia_lugares` — sin datos en Silver por motivos ya documentados, no
  necesitan limpieza.
- NO desactives ningún trigger de este grupo.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/077-...md`, aunque no completes los 5 — un resultado parcial
  documentado es mucho más útil que un intento perdido sin comitear nada
  (el motivo por el que las tareas 073/075/076 tuvieron que recuperarse a
  mano).

## Criterios de aceptación

- Confirmado con Athena si `aforos_peatones_bicicletas`, `ruido` y
  `cams_calidad_aire` tienen duplicación real o no.
- `agenda_eventos` y `bluesky_menciones` limpios y verificados (`n=1`).
- Cualquier otro dataset con duplicación confirmada en el paso 1, limpio y
  verificado si el presupuesto lo permite.
- `doc/077-limpieza-duplicados-grupo-diario.md` documenta el resultado con
  números reales.
- Hay un commit real con estos cambios.
