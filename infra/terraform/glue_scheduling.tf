# ---------------------------------------------------------------------------
# Tarea 064: scheduling de Silver/Gold para los 14 datasets -- SOLO diseño y
# código, sin `terraform apply` (mismo patrón que la tarea 041 con el
# piloto, o la 029 con Lambda/EventBridge antes de aplicarse en la 030).
# `terraform plan`/`apply` de este fichero quedan para una tarea posterior.
#
# Por qué un fichero separado de `glue.tf` (6800+ líneas): ese fichero ya
# agrupa, en bloques secuenciales por tarea, el rol IAM + catálogo + los dos
# `aws_glue_job` de cada uno de los 14 datasets. Meter aquí además los 28
# `aws_glue_trigger` (2 por dataset) mezclados con esos bloques haría aún
# más difícil de navegar un fichero ya muy largo. Este fichero reúne toda la
# lógica de orquestación (cadencia + encadenado condicional) en un único
# sitio, referenciando los jobs ya definidos en `glue.tf` por el propio
# recurso Terraform (`aws_glue_job.<x>.name`, no un string reconstruido a
# mano) para que un trigger nunca quede apuntando en silencio a un job
# renombrado.
#
# Mecanismo elegido: `aws_glue_trigger` nativo de Glue, no Step Functions ni
# EventBridge Scheduler invocando la API de Glue -- mismo principio de
# coste/complejidad mínima que el resto del proyecto (Glue no cobra por el
# trigger en sí, solo por el DPU-hora de los jobs que lanza; añadir una capa
# de orquestación externa sería complejidad sin beneficio). Dos triggers por
# dataset:
#   - Uno `SCHEDULED` (cron) que lanza el job Bronze->Silver.
#   - Uno `CONDITIONAL` encadenado (predicado: el job Bronze->Silver de ese
#     mismo dataset en estado `SUCCEEDED`) que lanza el job Silver->Gold --
#     así Silver->Gold nunca corre sobre un Silver a medias o corrupto; si
#     Bronze->Silver falla, esa ejecución simplemente no dispara Silver->Gold
#     (no hace falta workflow de Glue: un trigger CONDITIONAL standalone que
#     vigila el estado de un job y lanza otro es un patrón soportado
#     directamente por la API, sin agrupar ambos en un `aws_glue_workflow`).
# `start_on_creation = true` en los 28: quedan activos en cuanto se aplique
# este fichero, sin un paso manual adicional -- coherente con que ningún
# otro recurso de este proyecto (p.ej. `aws_scheduler_schedule` de
# `lambda.tf`) necesita activación manual.
#
# `aemet_prevision_avisos` comparte una única pareja de triggers (no dos
# independientes) porque -- a diferencia de Bronze, donde Lambda sí separa
# "previsión" y "avisos" en `local.schedules` con cadencias distintas --
# Silver/Gold de este dataset ya es un único job Glue por etapa
# (`aws_glue_job.aemet_prevision_avisos_bronze_to_silver` /
# `..._silver_to_gold`, tarea 058) que procesa ambas formas en la misma
# ejecución y escribe a los dos destinos Gold correspondientes (confirmado
# en `doc/063-verificar-silver-gold-lote2-completo-parte2.md`) -- no hay dos
# jobs entre los que repartir triggers.
#
# LIMITACIÓN IMPORTANTE, verificada contra la documentación de AWS: a
# diferencia de `aws_scheduler_schedule` (EventBridge Scheduler, usado por
# `lambda.tf` para Bronze), el campo `schedule` de `aws_glue_trigger` NO
# admite zona horaria -- un cron SCHEDULED de Glue se interpreta SIEMPRE en
# UTC, sin parámetro para cambiarlo. Por eso todos los cron de este fichero
# están en UTC, no en `Europe/Madrid` como los de `local.schedules`.
#   - Grupo horario: sin ajuste. "Cada hora, minuto 10" es la misma cadencia
#     en cualquier zona horaria -- el desfase Madrid-UTC es siempre un
#     número entero de horas (+1 CET / +2 CEST), nunca una fracción, así que
#     el minuto no se desalinea entre zonas.
#   - Grupo diario: SÍ implica una limitación real. Un cron UTC fijo
#     representa las 08:00 hora de Madrid solo en una de las dos mitades del
#     año. Los cron de este fichero están calculados para caer a las 08:00
#     CEST (horario de verano, vigente en la fecha de esta tarea, agosto
#     2026); en horario de invierno (CET) la misma ejecución caerá una hora
#     más tarde en local (09:00 CET). No se corrige aquí (alternar dos cron
#     a mano dos veces al año excede el alcance de esta tarea, que pide
#     implementar la cadencia ya decidida, no diseñar un mecanismo de DST) --
#     un desfase de hasta una hora es aceptable para un job diario cuyo
#     único requisito es "haber corrido después del último Bronze del día"
#     (objetivo de análisis por hora/día, no tiempo real), y en las dos
#     estaciones sigue cumpliendo ese margen para los 8 datasets del grupo
#     (ver el detalle de cada uno más abajo).
# ---------------------------------------------------------------------------

locals {
  # Job de Bronze->Silver y Silver->Gold de cada dataset, referenciados por
  # el propio recurso Terraform ya definido en `glue.tf`.
  glue_bronze_to_silver_jobs = {
    trafico                    = aws_glue_job.trafico_bronze_to_silver
    transporte_publico_emt     = aws_glue_job.transporte_publico_emt_bronze_to_silver
    bicimad                    = aws_glue_job.bicimad_bronze_to_silver
    aparcamientos              = aws_glue_job.aparcamientos_bronze_to_silver
    calidad_aire               = aws_glue_job.calidad_aire_bronze_to_silver
    meteorologia               = aws_glue_job.meteorologia_bronze_to_silver
    ruido                      = aws_glue_job.ruido_bronze_to_silver
    cartelera_cines_estrenos   = aws_glue_job.cartelera_cines_estrenos_bronze_to_silver
    agenda_eventos             = aws_glue_job.agenda_eventos_bronze_to_silver
    bluesky_menciones          = aws_glue_job.bluesky_menciones_bronze_to_silver
    aemet_prevision_avisos     = aws_glue_job.aemet_prevision_avisos_bronze_to_silver
    cams_calidad_aire          = aws_glue_job.cams_calidad_aire_bronze_to_silver
    afluencia_lugares          = aws_glue_job.afluencia_lugares_bronze_to_silver
    aforos_peatones_bicicletas = aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver
  }

  glue_silver_to_gold_jobs = {
    trafico                    = aws_glue_job.trafico_silver_to_gold
    transporte_publico_emt     = aws_glue_job.transporte_publico_emt_silver_to_gold
    bicimad                    = aws_glue_job.bicimad_silver_to_gold
    aparcamientos              = aws_glue_job.aparcamientos_silver_to_gold
    calidad_aire               = aws_glue_job.calidad_aire_silver_to_gold
    meteorologia               = aws_glue_job.meteorologia_silver_to_gold
    ruido                      = aws_glue_job.ruido_silver_to_gold
    cartelera_cines_estrenos   = aws_glue_job.cartelera_cines_estrenos_silver_to_gold
    agenda_eventos             = aws_glue_job.agenda_eventos_silver_to_gold
    bluesky_menciones          = aws_glue_job.bluesky_menciones_silver_to_gold
    aemet_prevision_avisos     = aws_glue_job.aemet_prevision_avisos_silver_to_gold
    cams_calidad_aire          = aws_glue_job.cams_calidad_aire_silver_to_gold
    afluencia_lugares          = aws_glue_job.afluencia_lugares_silver_to_gold
    aforos_peatones_bicicletas = aws_glue_job.aforos_peatones_bicicletas_silver_to_gold
  }

  # Prefijo de nombre de cada dataset (para nombrar sus triggers) -- los
  # mismos locals `glue_<dataset>_prefix` ya definidos en `glue.tf`.
  glue_trigger_prefixes = {
    trafico                    = local.glue_trafico_prefix
    transporte_publico_emt     = local.glue_transporte_publico_emt_prefix
    bicimad                    = local.glue_bicimad_prefix
    aparcamientos              = local.glue_aparcamientos_prefix
    calidad_aire               = local.glue_calidad_aire_prefix
    meteorologia               = local.glue_meteorologia_prefix
    ruido                      = local.glue_ruido_prefix
    cartelera_cines_estrenos   = local.glue_cartelera_cines_estrenos_prefix
    agenda_eventos             = local.glue_agenda_eventos_prefix
    bluesky_menciones          = local.glue_bluesky_menciones_prefix
    aemet_prevision_avisos     = local.glue_aemet_prevision_avisos_prefix
    cams_calidad_aire          = local.glue_cams_calidad_aire_prefix
    afluencia_lugares          = local.glue_afluencia_lugares_prefix
    aforos_peatones_bicicletas = local.glue_aforos_peatones_bicicletas_prefix
  }

  # Grupo "casi tiempo real" (Bronze llega cada 5-15 min, ver
  # `local.schedules` de `lambda.tf`) -> Silver/Gold cada hora, minuto 10
  # (deja tiempo a que el Bronze de esa hora ya esté escrito: el más lento
  # de los seis, `aparcamientos`, llega cada 15 min; `calidad_aire`/
  # `meteorologia` llegan como muy tarde en el minuto 55 de cada hora).
  glue_trigger_hourly_datasets = [
    "trafico", "transporte_publico_emt", "bicimad",
    "aparcamientos", "calidad_aire", "meteorologia",
  ]
  glue_trigger_hourly_schedule = "cron(10 * * * ? *)"

  # Grupo "diario" (Bronze llega 1x/día o más espaciado -semanal/mensual-, o
  # el propio dataset ya es un agregado diario como `ruido`) -> Silver/Gold
  # 1x/día. Por defecto 08:00 CEST = 06:00 UTC (ver nota de zona horaria de
  # arriba). Dos excepciones, confirmadas contra `local.schedules` de
  # `lambda.tf`:
  #   - `cartelera_cines_estrenos`: su único Bronze del día llega a las
  #     08:00 Madrid (`local.schedules.cartelera_cines_estrenos`), el mismo
  #     instante que el valor por defecto -- se retrasa 15 min (06:15 UTC)
  #     para no competir con él.
  #   - `aemet_prevision_avisos`: su Bronze más tardío del día (avisos) *también*
  #     llega a las 08:00 Madrid (`local.schedules.aemet_avisos_0800`,
  #     aparte de los de 11:00/18:00/23:50 del día anterior) -- mismo motivo,
  #     se retrasa 15 min (06:15 UTC). El resto de datasets del grupo tienen
  #     su Bronze más tardío del día antes de las 08:00 Madrid (`ruido`
  #     07:00, `agenda_eventos`/`afluencia_lugares`/`aforos_peatones_bicicletas`
  #     06:00) o llegan de forma continua (`bluesky_menciones`, cada hora),
  #     así que 08:00/06:00 UTC no necesita ajuste para ellos.
  #   - `cams_calidad_aire` se define directamente en UTC en vez de convertir
  #     desde Madrid: su Bronze más tardío ya está expresado en UTC
  #     (`local.schedules.cams_0900_utc`, 09:00 UTC, precisamente para no
  #     depender del cambio de hora español) -- 15 min después, 09:15 UTC.
  glue_trigger_daily_datasets = {
    ruido                      = { schedule = "cron(0 6 * * ? *)" }
    agenda_eventos             = { schedule = "cron(0 6 * * ? *)" }
    bluesky_menciones          = { schedule = "cron(0 6 * * ? *)" }
    afluencia_lugares          = { schedule = "cron(0 6 * * ? *)" }
    aforos_peatones_bicicletas = { schedule = "cron(0 6 * * ? *)" }
    cartelera_cines_estrenos   = { schedule = "cron(15 6 * * ? *)" }
    aemet_prevision_avisos     = { schedule = "cron(15 6 * * ? *)" }
    cams_calidad_aire          = { schedule = "cron(15 9 * * ? *)" }
  }
}

# ---------------------------------------------------------------------------
# Grupo horario (6 datasets)
# ---------------------------------------------------------------------------

resource "aws_glue_trigger" "scheduled_bronze_to_silver_hourly" {
  for_each = toset(local.glue_trigger_hourly_datasets)

  name              = "${local.glue_trigger_prefixes[each.value]}-scheduled-bronze-to-silver"
  description       = "Lanza Bronze->Silver de ${each.value} cada hora, minuto 10 (tarea 064)."
  type              = "SCHEDULED"
  schedule          = local.glue_trigger_hourly_schedule
  start_on_creation = true

  actions {
    job_name = local.glue_bronze_to_silver_jobs[each.value].name
  }

  # `start_on_creation` es un argumento de solo escritura: la API de Glue
  # (GetTrigger) no lo devuelve, así que tras un `terraform import` (tarea
  # 065, ver `doc/065-aplicar-scheduling-silver-gold.md`) el estado no puede
  # refrescarlo y `terraform plan` lo marcaría como diff perpetuo aunque el
  # trigger ya esté `ACTIVATED` en AWS real -- se ignora explícitamente.
  lifecycle {
    ignore_changes = [start_on_creation]
  }
}

resource "aws_glue_trigger" "conditional_silver_to_gold_hourly" {
  for_each = toset(local.glue_trigger_hourly_datasets)

  name              = "${local.glue_trigger_prefixes[each.value]}-conditional-silver-to-gold"
  description       = "Lanza Silver->Gold de ${each.value} cuando su Bronze->Silver horario termina con éxito (tarea 064)."
  type              = "CONDITIONAL"
  start_on_creation = true

  actions {
    job_name = local.glue_silver_to_gold_jobs[each.value].name
  }

  predicate {
    conditions {
      job_name = local.glue_bronze_to_silver_jobs[each.value].name
      state    = "SUCCEEDED"
    }
  }

  lifecycle {
    ignore_changes = [start_on_creation]
  }
}

# ---------------------------------------------------------------------------
# Grupo diario (8 datasets)
# ---------------------------------------------------------------------------

resource "aws_glue_trigger" "scheduled_bronze_to_silver_daily" {
  for_each = local.glue_trigger_daily_datasets

  name              = "${local.glue_trigger_prefixes[each.key]}-scheduled-bronze-to-silver"
  description       = "Lanza Bronze->Silver de ${each.key} 1x/día (tarea 064)."
  type              = "SCHEDULED"
  schedule          = each.value.schedule
  start_on_creation = true

  actions {
    job_name = local.glue_bronze_to_silver_jobs[each.key].name
  }

  lifecycle {
    ignore_changes = [start_on_creation]
  }
}

resource "aws_glue_trigger" "conditional_silver_to_gold_daily" {
  for_each = local.glue_trigger_daily_datasets

  name              = "${local.glue_trigger_prefixes[each.key]}-conditional-silver-to-gold"
  description       = "Lanza Silver->Gold de ${each.key} cuando su Bronze->Silver diario termina con éxito (tarea 064)."
  type              = "CONDITIONAL"
  start_on_creation = true

  actions {
    job_name = local.glue_silver_to_gold_jobs[each.key].name
  }

  predicate {
    conditions {
      job_name = local.glue_bronze_to_silver_jobs[each.key].name
      state    = "SUCCEEDED"
    }
  }

  lifecycle {
    ignore_changes = [start_on_creation]
  }
}
