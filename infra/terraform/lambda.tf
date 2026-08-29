# ---------------------------------------------------------------------------
# Tarea 029: una función Lambda + un schedule de EventBridge Scheduler por
# cada productor de datos de `ingesta/capturas/` que ya tiene
# `lambda_handler` (tareas 026/027/028).
#
# Diseño general (ver doc/029-terraform-lambda-eventbridge-plan.md para el
# porqué de cada decisión):
#   - Un único paquete .zip de código fuente (`ingesta/`, sin dependencias de
#     terceros) reutilizado por las 14 funciones; solo cambia el `handler`.
#   - Las dependencias de terceros (requirements.txt) NO se empaquetan en
#     esta tarea (ver `var.lambda_dependencies_layer_arn`): esta EC2 tiene
#     muy poco disco libre y construir una layer compatible con Lambda para
#     paquetes con extensiones compiladas (netCDF4) requiere una herramienta
#     de build específica (Docker/manylinux), no un `pip install` directo
#     aquí. Queda documentado como pendiente antes del `apply` real.
#   - `local.producers`: una entrada por función Lambda (16, una por módulo
#     con `lambda_handler`; +`emt_incidencias`/`parques_jardines`/`ser_calles`
#     por FIL_03/04/05, -`afluencia_lugares` por FIL_06). `aemet_prevision_avisos.py`
#     es un único módulo que atiende tanto "avisos" como "previsión", así que
#     es una sola entrada aquí aunque la tabla de cadencias del enunciado la
#     liste como dos filas).
#   - `local.schedules`: una entrada por regla de EventBridge Scheduler (21
#     en total: 14 productores con 1 schedule cada uno, salvo
#     aemet_prevision_avisos con 6 —4 avisos + 2 previsión, mismo Lambda,
#     distinto `input`—, cams_calidad_aire con 2, y cartelera_cines_estrenos
#     con 2 —estrenos + sesiones, tarea 090, mismo Lambda, distinto
#     `input.tipo`—). Cada entrada referencia a qué productor apunta vía
#     `producer_key`.
# ---------------------------------------------------------------------------

locals {
  # Nombre corto de cada SSM SecureString con una credencial que alguna
  # función necesita. El valor real NUNCA vive en este repositorio (ver
  # `aws_ssm_parameter.secrets` más abajo y `var.ssm_secret_placeholder_value`).
  # FIL_06: `GOOGLE_MAPS_API_KEY` retirado junto con el productor
  # `afluencia_lugares`. Al quitarlo, `terraform apply` destruye su parámetro
  # SSM placeholder (nunca tuvo valor real).
  secrets = {
    EMT_CLIENT_ID    = "/${var.project_name}/${var.environment}/secrets/emt-client-id"
    EMT_PASS_KEY     = "/${var.project_name}/${var.environment}/secrets/emt-pass-key"
    AEMET_API_KEY    = "/${var.project_name}/${var.environment}/secrets/aemet-api-key"
    CAMS_ADS_API_KEY = "/${var.project_name}/${var.environment}/secrets/cams-ads-api-key"
    # Bluesky exige autenticación en `searchPosts` desde 2025: sesión de AT
    # Protocol con handle + App Password. `BLUESKY_IDENTIFIER` es el handle
    # público (no es un secreto en sí, pero se gestiona igual que el resto
    # para no añadir un mecanismo aparte); `BLUESKY_APP_PASSWORD` sí lo es.
    BLUESKY_IDENTIFIER   = "/${var.project_name}/${var.environment}/secrets/bluesky-identifier"
    BLUESKY_APP_PASSWORD = "/${var.project_name}/${var.environment}/secrets/bluesky-app-password"
  }

  # Una entrada por función Lambda. `secret_env` lista los nombres de
  # `local.secrets` que esta función necesita como variable de entorno
  # (mismo nombre de variable que ya lee cada módulo vía `os.environ`).
  producers = {
    trafico = {
      module      = "trafico_madrid"
      dataset     = "trafico"
      description = "Intensidad de tráfico de Madrid (Informo) -> Bronze/trafico"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    transporte_publico_emt = {
      module      = "transporte_publico_madrid"
      dataset     = "transporte_publico_emt"
      description = "Llegadas EMT Madrid (MobilityLabs) -> Bronze/transporte_publico_emt"
      timeout     = 30
      memory_mb   = 256
      secret_env  = ["EMT_CLIENT_ID", "EMT_PASS_KEY"]
    }
    bicimad = {
      module      = "bicimad"
      dataset     = "bicimad"
      description = "Estado de estaciones BiciMAD (GBFS) -> Bronze/bicimad"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    aparcamientos = {
      module      = "aparcamientos_madrid"
      dataset     = "aparcamientos"
      description = "Ocupación de aparcamientos de Madrid (SOAP, 1 llamada por aparcamiento) -> Bronze/aparcamientos"
      timeout     = 180
      memory_mb   = 256
      secret_env  = []
    }
    calidad_aire = {
      module      = "calidad_aire_madrid"
      dataset     = "calidad_aire"
      description = "Calidad del aire de Madrid (estaciones municipales) -> Bronze/calidad_aire"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    meteorologia = {
      module      = "meteorologia_madrid"
      dataset     = "meteorologia"
      description = "Meteorología de Madrid (estaciones municipales) -> Bronze/meteorologia"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    ruido = {
      module      = "ruido_madrid"
      dataset     = "ruido"
      description = "Ruido de Madrid (estaciones municipales, último día disponible) -> Bronze/ruido"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    # FIL_06: `afluencia_lugares` (Google Popular Times) retirado. Coste 0
    # imposible (tarea 083), la Lambda fallaba en cada ejecución programada
    # por falta de `GOOGLE_MAPS_API_KEY`, y el Gold estaba a 0 filas. Se
    # sustituye por una señal derivada de sensores vía el grafo (tarea 089),
    # materializada por un job aparte -- ver `procesamiento/afluencia_lugares/`
    # y `doc/FIL-06-*.md`. Al quitar esta entrada, `terraform apply` destruye
    # la función Lambda, su log group y su schedule.
    aforos_peatones_bicicletas = {
      module      = "aforos_peatones_bicicletas_madrid"
      module      = "aforos_peatones_bicicletas_madrid"
      dataset     = "aforos_peatones_bicicletas"
      description = "Aforos de peatones/bicicletas de Madrid (último día disponible) -> Bronze/aforos_peatones_bicicletas"
      # 120s se quedaba corto en el entorno de red real de Lambda para
      # descargar los dos CSV completos de este dataset (~17-34 MB, ver
      # diagnóstico tarea 040): la Lambda se colgaba en silencio hasta el
      # timeout, sin ningún error de red, porque un único timeout float de
      # `requests` no cubre una descarga lenta pero continua. 300s (mismo
      # valor que `afluencia_lugares`, la otra función de este proyecto con
      # timeout ampliado) da margen de sobra incluso con reintentos; 512 MB
      # (el doble) da más CPU/ancho de banda proporcional para la descarga y
      # el parseo de los CSV completos.
      timeout    = 300
      memory_mb  = 512
      secret_env = []
    }
    bluesky_menciones = {
      module      = "bluesky_menciones_madrid"
      dataset     = "bluesky_menciones"
      description = "Barrido de menciones de Bluesky por distrito/evento -> Bronze/bluesky_menciones"
      timeout     = 180
      memory_mb   = 256
      secret_env  = ["BLUESKY_IDENTIFIER", "BLUESKY_APP_PASSWORD"]
    }
    agenda_eventos = {
      module      = "agenda_eventos_madrid"
      dataset     = "agenda_eventos"
      description = "Agenda de eventos municipal + esMadrid (captura completa) -> Bronze/agenda_eventos"
      timeout     = 180
      memory_mb   = 256
      secret_env  = []
    }
    aemet_prevision_avisos = {
      module      = "aemet_prevision_avisos"
      dataset     = "aemet_prevision / aemet_avisos (según event.tipo)"
      description = "Previsión/avisos AEMET Madrid; decide dataset según event.tipo -> Bronze/aemet_prevision o Bronze/aemet_avisos"
      timeout     = 60
      memory_mb   = 256
      secret_env  = ["AEMET_API_KEY"]
    }
    cams_calidad_aire = {
      module      = "cams_calidad_aire_madrid"
      dataset     = "cams_calidad_aire"
      description = "Previsión de calidad del aire UE (Copernicus CAMS, NetCDF) -> Bronze/cams_calidad_aire"
      timeout     = 600
      memory_mb   = 512
      secret_env  = ["CAMS_ADS_API_KEY"]
    }
    cartelera_cines_estrenos = {
      module      = "cartelera_cines_madrid"
      dataset     = "cartelera_cines_estrenos"
      description = "Estrenos o sesiones de cine de Madrid (SensaCine), según event.tipo -> Bronze/cartelera_cines_estrenos"
      timeout     = 180
      memory_mb   = 256
      secret_env  = []
    }
    # FIL_03/04/05: los tres productores de la tarea 090 pasan de "muestra
    # commiteada" a productor real (handler + BronzeWriter añadidos en
    # FIL_02). Solo capa de Ingesta -> Bronze; Silver/Gold es trabajo aparte
    # (para `parques_jardines` se lee Bronze directo en `grafo/extract.py`,
    # mismo criterio que `poi_madrid`).
    emt_incidencias = {
      module      = "emt_incidencias_madrid"
      dataset     = "emt_incidencias"
      description = "Incidencias/alteraciones del servicio de EMT Madrid (feed RSS en vivo) -> Bronze/emt_incidencias"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    parques_jardines = {
      module      = "parques_jardines_madrid"
      dataset     = "parques_jardines"
      description = "Parques y jardines municipales de Madrid (referencia) -> Bronze/parques_jardines"
      timeout     = 60
      memory_mb   = 256
      secret_env  = []
    }
    ser_calles = {
      module      = "ser_calles_madrid"
      dataset     = "ser_calles"
      description = "Calles/plazas del Servicio de Estacionamiento Regulado (SER) de Madrid (referencia) -> Bronze/ser_calles"
      # ~34.500 tramos: descarga un CSV de varios MB y lo parsea entero. Mismo
      # perfil que aforos (300s/512MB), no el de los productores ligeros.
      timeout    = 300
      memory_mb  = 512
      secret_env = []
    }
  }

  # Una entrada por regla de EventBridge Scheduler. `producer_key` referencia
  # una clave de `local.producers`. `timezone` sigue la recomendación del
  # enunciado: "Europe/Madrid" para todo lo anclado a hora peninsular (evita
  # convertir a mano el cambio de hora), UTC explícito solo para CAMS. Las
  # expresiones `rate(...)` no dependen de zona horaria; se deja `timezone`
  # en null para esas y el proveedor usa su valor por defecto (UTC, sin
  # efecto real sobre un `rate`).
  schedules = {
    trafico = {
      producer_key = "trafico"
      expression   = "rate(5 minutes)"
      timezone     = null
      input        = null
    }
    emt_llegadas = {
      producer_key = "transporte_publico_emt"
      expression   = "rate(5 minutes)"
      timezone     = null
      input        = null
    }
    bicimad = {
      producer_key = "bicimad"
      expression   = "rate(5 minutes)"
      timezone     = null
      input        = null
    }
    aparcamientos = {
      producer_key = "aparcamientos"
      expression   = "rate(15 minutes)"
      timezone     = null
      input        = null
    }
    calidad_aire = {
      producer_key = "calidad_aire"
      expression   = "cron(15,35,55 * * * ? *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    meteorologia = {
      producer_key = "meteorologia"
      expression   = "cron(15,35,55 * * * ? *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    ruido = {
      # 1x/día, solo laborables, 07:00 hora de Madrid.
      producer_key = "ruido"
      expression   = "cron(0 7 ? * MON-FRI *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    # FIL_06: schedule de `afluencia_lugares` (Google Popular Times) retirado
    # junto con su productor -- ver el comentario en `local.producers`.
    aforos_peatones_bicicletas = {
      # 1x/mes, día 1 a las 06:00 hora de Madrid.
      producer_key = "aforos_peatones_bicicletas"
      expression   = "cron(0 6 1 * ? *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    bluesky_menciones = {
      producer_key = "bluesky_menciones"
      expression   = "rate(1 hour)"
      timezone     = null
      input        = null
    }
    agenda_eventos = {
      # 1x/día, 06:00 hora de Madrid.
      producer_key = "agenda_eventos"
      expression   = "cron(0 6 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    # AEMET avisos: 4 ventanas reales de emisión de AEMET (~08:00, ~11:00,
    # ~18:00 y 23:50 hora de Madrid), mismo Lambda que "previsión", distinto
    # `input.tipo`.
    aemet_avisos_0800 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(0 8 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "avisos" }
    }
    aemet_avisos_1100 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(0 11 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "avisos" }
    }
    aemet_avisos_1800 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(0 18 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "avisos" }
    }
    aemet_avisos_2350 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(50 23 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "avisos" }
    }
    # AEMET previsión: 2x/día, 07:00 y 14:00 hora de Madrid.
    aemet_prevision_0700 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(0 7 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "prevision" }
    }
    aemet_prevision_1400 = {
      producer_key = "aemet_prevision_avisos"
      expression   = "cron(0 14 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "prevision" }
    }
    # CAMS: 2 schedules en UTC (tras las tandas reales de CAMS a las
    # 06:45/08:30 UTC).
    cams_0715_utc = {
      producer_key = "cams_calidad_aire"
      expression   = "cron(15 7 * * ? *)"
      timezone     = "UTC"
      input        = null
    }
    cams_0900_utc = {
      producer_key = "cams_calidad_aire"
      expression   = "cron(0 9 * * ? *)"
      timezone     = "UTC"
      input        = null
    }
    cartelera_cines_estrenos = {
      # 1x/día, 08:00 hora de Madrid.
      producer_key = "cartelera_cines_estrenos"
      expression   = "cron(0 8 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    # Tarea 090: 1x/día, 07:00 hora de Madrid -- antes que el barrido de
    # estrenos (08:00), para que la mayor parte de las sesiones del día
    # sigan siendo futuras respecto a `captured_at` cuando la puerta de
    # calidad de Silver las evalúe (`showtime_already_passed`, ver
    # `procesamiento/silver_gold/cartelera_cines_estrenos/transform.py`).
    # Mismo Lambda que el schedule de arriba, `input.tipo` distinto -- mismo
    # patrón que aemet_prevision_avisos.
    cartelera_cines_estrenos_sesiones = {
      producer_key = "cartelera_cines_estrenos"
      expression   = "cron(0 7 * * ? *)"
      timezone     = "Europe/Madrid"
      input        = { tipo = "sesiones" }
    }
    # FIL_03: feed en vivo, cambia varias veces al día -> cada 30 min.
    emt_incidencias = {
      producer_key = "emt_incidencias"
      expression   = "rate(30 minutes)"
      timezone     = null
      input        = null
    }
    # FIL_04/05: datos de referencia (la fuente SER se actualiza
    # trimestralmente; los parques casi nunca) -> 1x/semana, lunes madrugada.
    parques_jardines = {
      producer_key = "parques_jardines"
      expression   = "cron(0 5 ? * MON *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
    ser_calles = {
      producer_key = "ser_calles"
      expression   = "cron(30 5 ? * MON *)"
      timezone     = "Europe/Madrid"
      input        = null
    }
  }

  function_name_by_producer = {
    for key, producer in local.producers :
    key => "${var.project_name}-${var.environment}-${key}"
  }

  # Ruta absoluta a `ingesta/` y lista de sus ficheros (relativos a esa
  # ruta), excluyendo `tests/`, `capturas/samples/` (fixtures/datos de
  # prueba, no código de producción) y cualquier `__pycache__/`/`.pyc`/
  # `.pyo` (bytecode cacheado por ejecuciones locales de los tests, nunca
  # commiteado -- ver .gitignore -- pero su presencia local hacía fallar
  # `terraform plan`/`apply` con "contents ... are not valid UTF-8", tarea
  # 092). `fileset` solo devuelve ficheros, no directorios.
  ingesta_source_root = "${path.module}/../../ingesta"
  ingesta_source_files = [
    for f in fileset(local.ingesta_source_root, "**") :
    f
    if !startswith(f, "tests/") && !startswith(f, "capturas/samples/") &&
    !strcontains(f, "__pycache__/") && !endswith(f, ".pyc") && !endswith(f, ".pyo")
  ]
}

# ---------------------------------------------------------------------------
# Paquete de código fuente (compartido por las 14 funciones)
#
# `source_dir` (usado hasta la tarea 030) empaqueta el *contenido* de
# `ingesta/` en la raíz del .zip, no el directorio `ingesta/` en sí, así que
# el `handler` de cada función (`ingesta.capturas.<módulo>.lambda_handler`)
# no encontraba el paquete `ingesta` al arrancar (`No module named
# 'ingesta'`, diagnosticado por la tarea 030 con una invocación real).
# Se sustituye por bloques `source` explícitos, uno por fichero, con
# `filename = "ingesta/<ruta-relativa>"`, para que `ingesta/` exista como
# carpeta de nivel superior dentro del .zip.
# ---------------------------------------------------------------------------

data "archive_file" "ingesta_source" {
  type        = "zip"
  output_path = "${path.module}/build/ingesta_source.zip"

  dynamic "source" {
    for_each = local.ingesta_source_files
    content {
      filename = "ingesta/${source.value}"
      content  = file("${local.ingesta_source_root}/${source.value}")
    }
  }
}

# ---------------------------------------------------------------------------
# Secretos: parámetros SSM SecureString con valor placeholder (nunca el
# secreto real). Cada función referencia directamente `.value` de los
# parámetros que necesita como variable de entorno (mismo nombre que ya lee
# `os.environ` en el módulo correspondiente); no hace falta que la función
# llame a SSM en tiempo de ejecución.
#
# `ignore_changes = [value]`: tras el primer `apply`, alguien fija el valor
# real a mano (`aws ssm put-parameter --overwrite`, fuera de Terraform y
# fuera de git); los `apply` siguientes no lo pisan con el placeholder.
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "secrets" {
  for_each = local.secrets

  name        = each.value
  type        = "SecureString"
  value       = var.ssm_secret_placeholder_value
  description = "Placeholder gestionado por Terraform para ${each.key} (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."

  lifecycle {
    ignore_changes = [value]
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Logs: un log group por función, con retención acotada (coste
# mínimo, y para no acumular logs indefinidamente).
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "producer" {
  for_each = local.producers

  name              = "/aws/lambda/${local.function_name_by_producer[each.key]}"
  retention_in_days = var.lambda_log_retention_days
}

# Amplía el rol de ingesta existente (aws_iam_role.ingestion, main.tf,
# tareas 001/015) con los permisos de CloudWatch Logs que toda Lambda
# necesita, acotados a los log groups de estas 14 funciones (nada más allá
# de eso y de la escritura en Bronze que ya tenía).
data "aws_iam_policy_document" "ingestion_lambda_logs" {
  statement {
    sid    = "WriteProducerLambdaLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [for lg in aws_cloudwatch_log_group.producer : "${lg.arn}:*"]
  }
}

resource "aws_iam_policy" "ingestion_lambda_logs" {
  name = "${var.project_name}-${var.environment}-ingestion-lambda-logs"

  description = "Permite a las funciones Lambda de productores escribir en sus propios log groups de CloudWatch Logs (tarea 029)."
  policy      = data.aws_iam_policy_document.ingestion_lambda_logs.json
}

resource "aws_iam_role_policy_attachment" "ingestion_lambda_logs" {
  role       = aws_iam_role.ingestion.name
  policy_arn = aws_iam_policy.ingestion_lambda_logs.arn
}

# ---------------------------------------------------------------------------
# Funciones Lambda de los productores
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "producer" {
  for_each = local.producers

  function_name = local.function_name_by_producer[each.key]
  description   = each.value.description

  role    = aws_iam_role.ingestion.arn
  handler = "ingesta.capturas.${each.value.module}.lambda_handler"
  runtime = var.lambda_runtime

  filename         = data.archive_file.ingesta_source.output_path
  source_code_hash = data.archive_file.ingesta_source.output_base64sha256

  timeout     = each.value.timeout
  memory_size = each.value.memory_mb

  layers = var.lambda_dependencies_layer_arn == null ? [] : [var.lambda_dependencies_layer_arn]

  environment {
    variables = merge(
      {
        BRONZE_BASE_PATH = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/"
      },
      { for name in each.value.secret_env : name => aws_ssm_parameter.secrets[name].value },
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.producer,
    aws_iam_role_policy_attachment.ingestion_lambda_logs,
  ]
}

# ---------------------------------------------------------------------------
# Rol IAM que EventBridge Scheduler asume para invocar cada Lambda. Distinto
# del rol de ejecución de la Lambda (aws_iam_role.ingestion): este solo
# necesita `lambda:InvokeFunction` sobre las funciones de esta tarea, nada
# de escritura en Bronze ni de logs.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name = "${var.project_name}-${var.environment}-scheduler-role"

  description        = "Rol asumido por EventBridge Scheduler para invocar las funciones Lambda de productores (tarea 029)."
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
}

data "aws_iam_policy_document" "scheduler_invoke_lambda" {
  statement {
    sid    = "InvokeProducerLambdas"
    effect = "Allow"

    actions   = ["lambda:InvokeFunction"]
    resources = [for fn in aws_lambda_function.producer : fn.arn]
  }
}

resource "aws_iam_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-${var.environment}-scheduler-invoke-lambda"

  description = "Permite a EventBridge Scheduler invocar exclusivamente las funciones Lambda de productores de esta tarea."
  policy      = data.aws_iam_policy_document.scheduler_invoke_lambda.json
}

resource "aws_iam_role_policy_attachment" "scheduler_invoke_lambda" {
  role       = aws_iam_role.scheduler.name
  policy_arn = aws_iam_policy.scheduler_invoke_lambda.arn
}

# ---------------------------------------------------------------------------
# Schedules de EventBridge Scheduler
# ---------------------------------------------------------------------------

resource "aws_scheduler_schedule" "producer" {
  for_each = local.schedules

  name = "${var.project_name}-${var.environment}-${each.key}"

  schedule_expression          = each.value.expression
  schedule_expression_timezone = each.value.timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.producer[each.value.producer_key].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = each.value.input == null ? null : jsonencode(each.value.input)
  }
}
