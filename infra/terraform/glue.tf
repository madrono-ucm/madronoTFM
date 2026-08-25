# ---------------------------------------------------------------------------
# Tarea 041: piloto Bronze -> Silver -> Gold de tráfico con AWS Glue.
#
# Alcance de ESTA tarea: solo escribir el código y la infraestructura, sin
# aplicarla (ver doc/041-piloto-silver-gold-trafico.md y el enunciado de la
# tarea) -- mismo patrón que la tarea 001 con el lakehouse. `terraform plan`/
# `apply` de este fichero quedan para una tarea posterior con revisión de
# plan de por medio (patrón de las tareas 014/015).
#
# Por qué AWS Glue y no un clúster Spark persistente (EMR, un Spark
# standalone en EC2...): coherente con el principio de coste mínimo ya
# aplicado en todo el proyecto (Lambda + EventBridge Scheduler para
# ingesta, un bucket S3 por capa sin ningún servidor en reposo). Glue es
# Spark *serverless*: se paga por DPU-hora solo mientras el job corre, sin
# ningún clúster que mantener encendido entre ejecuciones -- para un piloto
# de un único dataset procesado con una cadencia baja (horaria/diaria, no
# continua), un clúster EMR persistente estaría inactivo la inmensa mayoría
# del tiempo pagando por nada.
#
# Un único dataset piloto (`trafico`): dos jobs, uno por transformación
# (Bronze->Silver, Silver->Gold) -- no uno combinado, para poder reintentar/
# reejecutar cada etapa de forma independiente (p.ej. volver a agregar Gold
# sin releer y reprocesar Bronze) y para que cada job tenga un límite de
# tiempo/DPU ajustado a su propio coste computacional.
# ---------------------------------------------------------------------------

locals {
  glue_trafico_prefix = "${var.project_name}-${var.environment}-trafico"

  # Mismo patrón que `ingesta_source_files`/`data.archive_file.ingesta_source`
  # (lambda.tf, tarea 029): empaqueta todo `procesamiento/` (salvo `tests/`)
  # para que el job Bronze->Silver lo importe vía `--extra-py-files`
  # (`transform.bronze_to_silver`, `ge_suite.run_quality_report`), sin
  # duplicar la lógica de negocio entre este repo y el job real. Incluye
  # también `ge_suite.py`/`glue_*.py` aunque no todos los jobs los necesiten
  # (el job Silver->Gold no importa nada de este paquete, ver
  # `glue_silver_to_gold.py`): no tiene coste real empaquetar un par de
  # ficheros de más, y mantiene un único artefacto de librería para todo el
  # dataset en vez de tener que armar un .zip distinto por job.
  procesamiento_source_root = "${path.module}/../../procesamiento"
  procesamiento_source_files = [
    for f in fileset(local.procesamiento_source_root, "**") :
    f
    if !startswith(f, "tests/") && !strcontains(f, "__pycache__")
  ]
}

data "archive_file" "procesamiento_source" {
  type        = "zip"
  output_path = "${path.module}/build/procesamiento_source.zip"

  dynamic "source" {
    for_each = local.procesamiento_source_files
    content {
      filename = "procesamiento/${source.value}"
      content  = file("${local.procesamiento_source_root}/${source.value}")
    }
  }
}

# ---------------------------------------------------------------------------
# Artefactos del job (script + librería común) en el bucket de artefactos de
# build ya existente (tarea 032, `aws_s3_bucket.build_artifacts`) -- reutilizado
# a propósito en vez de crear un bucket nuevo solo para dos ficheros .py y un
# .zip pequeño: incluye el hash del contenido en la key, así que un cambio en
# el código sube a una key nueva sin pisar la anterior (mismo motivo que
# `layer_source_key` en lambda_layer_build.tf).
# ---------------------------------------------------------------------------

resource "aws_s3_object" "procesamiento_source" {
  bucket = aws_s3_bucket.build_artifacts.id
  key    = "glue-libs/procesamiento-${data.archive_file.procesamiento_source.output_md5}.zip"
  source = data.archive_file.procesamiento_source.output_path

  etag = data.archive_file.procesamiento_source.output_md5
}

resource "aws_s3_object" "glue_script_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/trafico_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/trafico/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/trafico/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/trafico/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/trafico_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/trafico/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/trafico/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/trafico/glue_silver_to_gold.py")
}

# ---------------------------------------------------------------------------
# Rol IAM de los jobs de Glue. Permisos mínimos: la política gestionada por
# AWS (`AWSGlueServiceRole`) para lo que todo job de Glue necesita en su
# propio nombre (API de Glue, CloudWatch Logs bajo `/aws-glue/...`), más
# políticas propias acotadas por prefijo a exactamente lo que este piloto
# necesita -- ni un permiso más:
#   - Bronze: solo lectura, solo bajo `trafico/` (no todo el bucket).
#   - Silver: lectura+escritura, solo bajo `trafico/` (Bronze->Silver
#     escribe; Silver->Gold lee del mismo prefijo).
#   - Gold: solo escritura, solo bajo `trafico_por_punto_hora/`.
#   - Bucket de artefactos: solo lectura, solo bajo `glue-scripts/` y
#     `glue-libs/` (el script y la librería común de este job).
#   - Catálogo de Glue: crear/actualizar particiones y tablas de las dos
#     tablas de este dataset (si el job las gestiona vía `enableUpdateCatalog`
#     en una tarea futura; se deja el permiso ya acotado por si acaso, no
#     se usa todavía en el `default_arguments` de esta tarea).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "glue_trafico_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_trafico" {
  name = "${local.glue_trafico_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue del piloto Bronze->Silver->Gold de tráfico (tarea 041)."
  assume_role_policy = data.aws_iam_policy_document.glue_trafico_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_trafico_service_role" {
  role       = aws_iam_role.glue_trafico.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_trafico_data_access" {
  statement {
    sid    = "ReadBronzeTrafico"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/trafico/*"]
  }

  statement {
    sid    = "ReadWriteSilverTrafico"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/trafico/*"]
  }

  # Informe de calidad de Great Expectations (tarea 051 arregló su escritura
  # vía `boto3.put_object` directo, pero nunca se concedió el permiso IAM
  # sobre este prefijo -- confirmado como bloqueante real en el job de
  # sanidad de la 051, `AccessDenied` en `s3:PutObject` sobre
  # `_quality_reports/trafico/*`).
  statement {
    sid    = "WriteSilverQualityReportsTrafico"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/trafico/*"]
  }

  statement {
    sid    = "WriteGoldTraficoPorPuntoHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # El segundo recurso cubre el marcador de directorio vacío
    # `<prefijo>_$folder$` que EMRFS escribe en la raíz del prefijo cuando el
    # DataFrame de Gold sale sin filas (job de sanidad de la tarea 052:
    # `AccessDenied` real en un `aparcamientos_por_parking_hora_$folder$`
    # ausente de la política -- el patrón `<prefijo>/*` no lo cubre, falta la
    # barra). Se añade a los 6 datasets por construcción idéntica del
    # committer, no solo al que falló.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/trafico_por_punto_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/trafico_por_punto_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForTraficoPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "trafico/*",
        "trafico_por_punto_hora/*",
        "_quality_reports/trafico/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir` que exige todo job de Glue (shuffle spill,
  # ficheros temporales de escritura) -- mismo bucket Silver, prefijo
  # `glue-temp/`, para no crear un bucket nuevo solo para esto.
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogTraficoTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_trafico_data_access" {
  name = "${local.glue_trafico_prefix}-data-access"

  description = "Acceso mínimo (lectura/escritura acotada por prefijo) del piloto Bronze->Silver->Gold de tráfico a los buckets del lakehouse y al catálogo de Glue (tarea 041)."
  policy      = data.aws_iam_policy_document.glue_trafico_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_trafico_data_access" {
  role       = aws_iam_role.glue_trafico.name
  policy_arn = aws_iam_policy.glue_trafico_data_access.arn
}

# ---------------------------------------------------------------------------
# Catálogo de datos de Glue: una base de datos por capa (silver/gold, Bronze
# no se cataloga -- son lotes JSON crudos sin un esquema único garantizado
# entre productores, no pensados para consultarse vía Athena/SQL), y una
# tabla por dataset dentro de cada una. Permite consultar Silver/Gold con
# Athena sin ningún paso adicional, y sienta el patrón de nombres
# (`<capa>_lakehouse` de base de datos, `<dataset>` o `<dataset>_<grano>` de
# tabla) para cuando se extienda a más fuentes.
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "silver" {
  name        = "${var.project_name}_${var.environment}_silver"
  description = "Capa Silver del lakehouse (datos limpios, reproyectados y validados)."
}

resource "aws_glue_catalog_database" "gold" {
  name        = "${var.project_name}_${var.environment}_gold"
  description = "Capa Gold del lakehouse (datos agregados, listos para consumo analítico)."
}

resource "aws_glue_catalog_table" "trafico_silver" {
  name          = "trafico"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Intensidad de tráfico de Madrid, limpia/reproyectada/validada (tarea 041)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/trafico/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/trafico/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "point_id"
      type = "string"
    }
    columns {
      name = "subarea"
      type = "string"
    }
    columns {
      name = "description"
      type = "string"
    }
    columns {
      name = "access_code"
      type = "string"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "location"
      type = "struct<x:double,y:double,srid_source:string,lat:double,lon:double,srid_target:string>"
    }
    columns {
      name = "intensity_vph"
      type = "int"
    }
    columns {
      name = "occupancy_pct"
      type = "int"
    }
    columns {
      name = "load_pct"
      type = "int"
    }
    columns {
      name = "service_level"
      type = "int"
    }
    columns {
      name = "saturation_intensity_vph"
      type = "int"
    }
    columns {
      name = "occupancy_ratio"
      type = "double"
    }
    columns {
      name = "load_ratio"
      type = "double"
    }
    columns {
      name = "intensity_ratio"
      type = "double"
    }
  }
}

resource "aws_glue_catalog_table" "trafico_gold" {
  name          = "trafico_por_punto_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Intensidad de tráfico de Madrid agregada por punto de medida y hora (tarea 041)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/trafico_por_punto_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/trafico_por_punto_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "point_id"
      type = "string"
    }
    columns {
      name = "subarea"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "avg_intensity_vph"
      type = "double"
    }
    columns {
      name = "max_intensity_vph"
      type = "int"
    }
    columns {
      name = "min_intensity_vph"
      type = "int"
    }
    columns {
      name = "avg_occupancy_ratio"
      type = "double"
    }
    columns {
      name = "avg_load_ratio"
      type = "double"
    }
    columns {
      name = "avg_intensity_ratio"
      type = "double"
    }
    columns {
      name = "avg_service_level"
      type = "double"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# Log group propio (además del que gestiona `AWSGlueServiceRole` bajo
# `/aws-glue/...`), para tener retención acotada por coste mínimo -- mismo
# criterio que `aws_cloudwatch_log_group.producer` en lambda.tf.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "glue_trafico" {
  name              = "/aws-glue/jobs/${local.glue_trafico_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

# ---------------------------------------------------------------------------
# Jobs de Glue
# ---------------------------------------------------------------------------

resource "aws_glue_job" "trafico_bronze_to_silver" {
  name        = "${local.glue_trafico_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de tráfico: reproyección EPSG:25830->WGS84, normalización, puerta de calidad (tarea 041)."

  role_arn          = aws_iam_role.glue_trafico.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    # Valores por defecto de los parámetros del job (ver docstring de
    # glue_bronze_to_silver.py); se pueden sobrescribir en cada
    # `start-job-run` para acotar el rango de fechas a procesar.
    "--bronze_path"         = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/trafico/"
    "--silver_path"         = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/trafico/"
    "--quality_report_path" = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/trafico/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_trafico]
}

resource "aws_glue_job" "trafico_silver_to_gold" {
  name        = "${local.glue_trafico_prefix}-silver-to-gold"
  description = "Silver -> Gold de tráfico: media de intensidad/ocupación/carga por punto de medida y hora (tarea 041)."

  role_arn          = aws_iam_role.glue_trafico.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language" = "python"
    "--TempDir"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    # Tarea 072: el script importa `procesamiento.silver_gold.incremental`
    # (lectura incremental) -- sin este argumento, ese import fallaría con
    # ModuleNotFoundError al ejecutar en Glue (el paquete `procesamiento` no
    # está en el path por defecto, solo lo trae `--extra-py-files`).
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/trafico/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/trafico_por_punto_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_trafico]
}

# ---------------------------------------------------------------------------
# Tarea 046: mismo patrón Bronze -> Silver -> Gold con AWS Glue, aplicado al
# segundo dataset (`transporte_publico_emt`, llegadas de autobús de la EMT
# Madrid, ver doc/003, doc/024 y `procesamiento/silver_gold/transporte_publico_emt/`).
# Alcance de ESTA tarea: igual que la 041, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para una
# tarea posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/transporte_publico_emt/*`, `silver/transporte_publico_emt/*`,
# `gold/transporte_publico_emt_por_parada_hora/*`) -- no se comparte el rol
# `glue_trafico`, mismo principio de mínimo privilegio por dataset que ya
# aplicaba `ingesta` (ver `procesamiento/README.md`, "Relevante para tareas
# futuras" de la tarea 041).
# ---------------------------------------------------------------------------

locals {
  glue_transporte_publico_emt_prefix = "${var.project_name}-${var.environment}-transporte-publico-emt"
}

resource "aws_s3_object" "glue_script_transporte_publico_emt_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/transporte_publico_emt_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_transporte_publico_emt_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/transporte_publico_emt_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_transporte_publico_emt_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_transporte_publico_emt" {
  name = "${local.glue_transporte_publico_emt_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de transporte publico EMT (tarea 046)."
  assume_role_policy = data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_transporte_publico_emt_service_role" {
  role       = aws_iam_role.glue_transporte_publico_emt.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_transporte_publico_emt_data_access" {
  statement {
    sid    = "ReadBronzeTransportePublicoEmt"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/transporte_publico_emt/*"]
  }

  statement {
    sid    = "ReadWriteSilverTransportePublicoEmt"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/transporte_publico_emt/*"]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsTransportePublicoEmt"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/transporte_publico_emt/*"]
  }

  statement {
    sid    = "WriteGoldTransportePublicoEmtPorParadaHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/transporte_publico_emt_por_parada_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/transporte_publico_emt_por_parada_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForTransportePublicoEmtPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "transporte_publico_emt/*",
        "transporte_publico_emt_por_parada_hora/*",
        "_quality_reports/transporte_publico_emt/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que `glue_trafico_data_access`:
  # bucket Silver, prefijo `glue-temp/` (compartido entre datasets -- no es
  # dato persistente, solo shuffle spill/ficheros temporales de escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogTransportePublicoEmtTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_transporte_publico_emt_data_access" {
  name = "${local.glue_transporte_publico_emt_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de transporte publico EMT a los buckets del lakehouse y al catalogo de Glue (tarea 046)."
  policy      = data.aws_iam_policy_document.glue_transporte_publico_emt_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_transporte_publico_emt_data_access" {
  role       = aws_iam_role.glue_transporte_publico_emt.name
  policy_arn = aws_iam_policy.glue_transporte_publico_emt_data_access.arn
}

resource "aws_glue_catalog_table" "transporte_publico_emt_silver" {
  name          = "transporte_publico_emt"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Llegadas de autobus EMT Madrid, limpias/validadas (tarea 046)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "stop_id"
      type = "string"
    }
    columns {
      name = "line"
      type = "string"
    }
    columns {
      name = "bus_id"
      type = "bigint"
    }
    columns {
      name = "destination"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "estimate_arrive_sec"
      type = "int"
    }
    columns {
      name = "distance_bus_m"
      type = "int"
    }
    columns {
      name = "is_head"
      type = "boolean"
    }
    columns {
      name = "deviation_sec"
      type = "int"
    }
    columns {
      name = "position_type_bus"
      type = "string"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string>"
    }
  }
}

resource "aws_glue_catalog_table" "transporte_publico_emt_gold" {
  name          = "transporte_publico_emt_por_parada_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Llegadas de autobus EMT Madrid agregadas por parada, linea y hora (tarea 046)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/transporte_publico_emt_por_parada_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/transporte_publico_emt_por_parada_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "stop_id"
      type = "string"
    }
    columns {
      name = "line"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_ingested_at"
      type = "string"
    }
    columns {
      name = "last_ingested_at"
      type = "string"
    }
    columns {
      name = "avg_estimate_arrive_sec"
      type = "double"
    }
    columns {
      name = "min_estimate_arrive_sec"
      type = "int"
    }
    columns {
      name = "max_estimate_arrive_sec"
      type = "int"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_transporte_publico_emt" {
  name              = "/aws-glue/jobs/${local.glue_transporte_publico_emt_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "transporte_publico_emt_bronze_to_silver" {
  name        = "${local.glue_transporte_publico_emt_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de transporte publico EMT: normalizacion, puerta de calidad (tarea 046)."

  role_arn          = aws_iam_role.glue_transporte_publico_emt.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_transporte_publico_emt_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/transporte_publico_emt/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/transporte_publico_emt/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_transporte_publico_emt]
}

resource "aws_glue_job" "transporte_publico_emt_silver_to_gold" {
  name        = "${local.glue_transporte_publico_emt_prefix}-silver-to-gold"
  description = "Silver -> Gold de transporte publico EMT: espera media/minima por parada, linea y hora (tarea 046)."

  role_arn          = aws_iam_role.glue_transporte_publico_emt.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_transporte_publico_emt_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/transporte_publico_emt_por_parada_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_transporte_publico_emt]
}

# Jobs de un solo uso (tarea 075) para reconstruir Silver/Gold de `transporte_publico_emt`
# desde cero, deduplicado -- ver docstring de `glue_backfill_dedup.py`. Sin
# trigger ni schedule: se lanzan a mano, una vez.
resource "aws_s3_object" "glue_script_transporte_publico_emt_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/transporte_publico_emt_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup.py")
}

resource "aws_glue_job" "transporte_publico_emt_silver_backfill_dedup" {
  name        = "${local.glue_transporte_publico_emt_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion deduplicada de Silver de transporte_publico_emt desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_transporte_publico_emt.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/transporte_publico_emt/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/transporte_publico_emt/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_transporte_publico_emt]
}

resource "aws_s3_object" "glue_script_transporte_publico_emt_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/transporte_publico_emt_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/transporte_publico_emt/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "transporte_publico_emt_gold_backfill_dedup" {
  name        = "${local.glue_transporte_publico_emt_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion completa de Gold de transporte_publico_emt desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_transporte_publico_emt.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/transporte_publico_emt/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/transporte_publico_emt_por_parada_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_transporte_publico_emt]
}

# ---------------------------------------------------------------------------
# Tarea 047: mismo patrón Bronze -> Silver -> Gold con AWS Glue, aplicado al
# tercer dataset (`bicimad`, estado de estaciones de BiciMAD vía GBFS, ver
# doc/004, `ingesta/capturas/bicimad.py` y
# `procesamiento/silver_gold/bicimad/`). Alcance de ESTA tarea: igual que la
# 041/046, solo código/infraestructura, sin `terraform apply` -- `terraform
# plan`/`apply` de este bloque quedan para una tarea posterior con revisión
# de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/bicimad/*`, `silver/bicimad/*`,
# `gold/bicimad_por_estacion_hora/*`) -- no se comparte ningún rol con
# `trafico`/`transporte_publico_emt`, mismo principio de mínimo privilegio
# por dataset que ya aplicaba `ingesta` (ver `procesamiento/README.md`).
# ---------------------------------------------------------------------------

locals {
  glue_bicimad_prefix = "${var.project_name}-${var.environment}-bicimad"
}

resource "aws_s3_object" "glue_script_bicimad_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bicimad_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bicimad/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_bicimad_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bicimad_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bicimad/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_bicimad_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_bicimad" {
  name = "${local.glue_bicimad_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de BiciMAD (tarea 047)."
  assume_role_policy = data.aws_iam_policy_document.glue_bicimad_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_bicimad_service_role" {
  role       = aws_iam_role.glue_bicimad.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_bicimad_data_access" {
  statement {
    sid    = "ReadBronzeBicimad"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/bicimad/*"]
  }

  statement {
    sid    = "ReadWriteSilverBicimad"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/bicimad/*"]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsBicimad"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/bicimad/*"]
  }

  statement {
    sid    = "WriteGoldBicimadPorEstacionHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/bicimad_por_estacion_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/bicimad_por_estacion_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForBicimadPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "bicimad/*",
        "bicimad_por_estacion_hora/*",
        "_quality_reports/bicimad/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que `glue_trafico_data_access`/
  # `glue_transporte_publico_emt_data_access`: bucket Silver, prefijo
  # `glue-temp/` (compartido entre datasets -- no es dato persistente, solo
  # shuffle spill/ficheros temporales de escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogBicimadTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_bicimad_data_access" {
  name = "${local.glue_bicimad_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de BiciMAD a los buckets del lakehouse y al catalogo de Glue (tarea 047)."
  policy      = data.aws_iam_policy_document.glue_bicimad_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_bicimad_data_access" {
  role       = aws_iam_role.glue_bicimad.name
  policy_arn = aws_iam_policy.glue_bicimad_data_access.arn
}

resource "aws_glue_catalog_table" "bicimad_silver" {
  name          = "bicimad"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Estado de estaciones de BiciMAD (GBFS), limpio/validado (tarea 047)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "bikes_available"
      type = "int"
    }
    columns {
      name = "bikes_disabled"
      type = "int"
    }
    columns {
      name = "docks_available"
      type = "int"
    }
    columns {
      name = "docks_disabled"
      type = "int"
    }
    columns {
      name = "docks_total"
      type = "int"
    }
    columns {
      name = "status"
      type = "string"
    }
    columns {
      name = "is_renting"
      type = "boolean"
    }
    columns {
      name = "is_returning"
      type = "boolean"
    }
    columns {
      name = "occupancy_ratio"
      type = "double"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string>"
    }
  }
}

resource "aws_glue_catalog_table" "bicimad_gold" {
  name          = "bicimad_por_estacion_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Estado de estaciones de BiciMAD agregado por estacion y hora (tarea 047)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bicimad_por_estacion_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bicimad_por_estacion_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "avg_bikes_available"
      type = "double"
    }
    columns {
      name = "avg_bikes_disabled"
      type = "double"
    }
    columns {
      name = "avg_docks_available"
      type = "double"
    }
    columns {
      name = "avg_docks_disabled"
      type = "double"
    }
    columns {
      name = "avg_occupancy_ratio"
      type = "double"
    }
    columns {
      name = "docks_total"
      type = "int"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_bicimad" {
  name              = "/aws-glue/jobs/${local.glue_bicimad_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "bicimad_bronze_to_silver" {
  name        = "${local.glue_bicimad_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de BiciMAD: normalizacion, puerta de calidad (tarea 047)."

  role_arn          = aws_iam_role.glue_bicimad.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bicimad_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/bicimad/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/bicimad/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bicimad]
}

# Job de un solo uso (tarea 073) para reconstruir Silver de `bicimad` desde
# cero, deduplicado -- ver docstring de `glue_backfill_dedup.py`. Sin
# trigger ni schedule: se lanza a mano, una vez.
resource "aws_s3_object" "glue_script_bicimad_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bicimad_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup.py")
}

resource "aws_glue_job" "bicimad_silver_backfill_dedup" {
  name        = "${local.glue_bicimad_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 073): reconstruccion deduplicada de Silver de bicimad desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_bicimad.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez, no una
  # sola particion horaria, y puede tardar mas que el pipeline incremental.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bicimad_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/bicimad/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/bicimad/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bicimad]
}

# Job de un solo uso (tarea 074) para reconstruir Gold de `bicimad` desde
# cero, tras la reconstrucción deduplicada de Silver (tarea 073). Sin
# trigger ni schedule: se lanza a mano, una vez.
resource "aws_s3_object" "glue_script_bicimad_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bicimad_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "bicimad_gold_backfill_dedup" {
  name        = "${local.glue_bicimad_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 074): reconstruccion completa de Gold de bicimad desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_bicimad.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el pipeline incremental (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Silver de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bicimad_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bicimad_por_estacion_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bicimad]
}

resource "aws_glue_job" "bicimad_silver_to_gold" {
  name        = "${local.glue_bicimad_prefix}-silver-to-gold"
  description = "Silver -> Gold de BiciMAD: disponibilidad media de bicis/anclajes por estacion y hora (tarea 047)."

  role_arn          = aws_iam_role.glue_bicimad.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bicimad_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language" = "python"
    "--TempDir"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    # Tarea 072: el script importa `procesamiento.silver_gold.incremental`
    # (lectura incremental) -- sin este argumento, ese import fallaría con
    # ModuleNotFoundError al ejecutar en Glue (el paquete `procesamiento` no
    # está en el path por defecto, solo lo trae `--extra-py-files`).
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bicimad/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bicimad_por_estacion_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bicimad]
}


# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (Glue, tarea 041/046/047 extendido a un CUARTO
# dataset (`aparcamientos`, ocupación de aparcamientos rotacionales de
# Madrid vía el servicio SOAP de datos.madrid.es, ver doc/005,
# `ingesta/capturas/aparcamientos_madrid.py` y
# `procesamiento/silver_gold/aparcamientos/`). Alcance de ESTA tarea: igual
# que la 041/046/047, solo código/infraestructura, sin `terraform apply` --
# `terraform plan`/`apply` de este bloque quedan para una tarea posterior
# con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/aparcamientos/*`, `silver/aparcamientos/*`,
# `gold/aparcamientos_por_parking_hora/*`) -- no se comparte ningún rol con
# `trafico`/`transporte_publico_emt`/`bicimad`, mismo principio de mínimo
# privilegio por dataset que ya aplicaba `ingesta` (ver
# `procesamiento/README.md`).
# ---------------------------------------------------------------------------

locals {
  glue_aparcamientos_prefix = "${var.project_name}-${var.environment}-aparcamientos"
}

resource "aws_s3_object" "glue_script_aparcamientos_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aparcamientos_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_aparcamientos_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aparcamientos_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_aparcamientos_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_aparcamientos" {
  name = "${local.glue_aparcamientos_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de aparcamientos rotacionales (tarea 048)."
  assume_role_policy = data.aws_iam_policy_document.glue_aparcamientos_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_aparcamientos_service_role" {
  role       = aws_iam_role.glue_aparcamientos.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_aparcamientos_data_access" {
  statement {
    sid    = "ReadBronzeAparcamientos"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/aparcamientos/*"]
  }

  statement {
    sid    = "ReadWriteSilverAparcamientos"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/aparcamientos/*"]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsAparcamientos"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/aparcamientos/*"]
  }

  statement {
    sid    = "WriteGoldAparcamientosPorParkingHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el que provocó el `AccessDenied` real, ver doc/052.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/aparcamientos_por_parking_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/aparcamientos_por_parking_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForAparcamientosPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "aparcamientos/*",
        "aparcamientos_por_parking_hora/*",
        "_quality_reports/aparcamientos/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets
  # -- no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogAparcamientosTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_aparcamientos_data_access" {
  name = "${local.glue_aparcamientos_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de aparcamientos rotacionales a los buckets del lakehouse y al catalogo de Glue (tarea 048)."
  policy      = data.aws_iam_policy_document.glue_aparcamientos_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_aparcamientos_data_access" {
  role       = aws_iam_role.glue_aparcamientos.name
  policy_arn = aws_iam_policy.glue_aparcamientos_data_access.arn
}

resource "aws_glue_catalog_table" "aparcamientos_silver" {
  name          = "aparcamientos"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Ocupación de aparcamientos rotacionales de Madrid, limpia/validada (tarea 048)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "parking_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "free_spaces"
      type = "int"
    }
    columns {
      name = "total_spaces"
      type = "int"
    }
    columns {
      name = "occupancy_ratio"
      type = "double"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string>"
    }
  }
}

resource "aws_glue_catalog_table" "aparcamientos_gold" {
  name          = "aparcamientos_por_parking_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Ocupación de aparcamientos rotacionales agregada por aparcamiento y hora (tarea 048)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aparcamientos_por_parking_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aparcamientos_por_parking_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "parking_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "avg_free_spaces"
      type = "double"
    }
    columns {
      name = "avg_occupancy_ratio"
      type = "double"
    }
    columns {
      name = "total_spaces"
      type = "int"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_aparcamientos" {
  name              = "/aws-glue/jobs/${local.glue_aparcamientos_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "aparcamientos_bronze_to_silver" {
  name        = "${local.glue_aparcamientos_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de aparcamientos rotacionales: normalizacion, puerta de calidad (tarea 048)."

  role_arn          = aws_iam_role.glue_aparcamientos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aparcamientos_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aparcamientos/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/aparcamientos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aparcamientos]
}

resource "aws_glue_job" "aparcamientos_silver_to_gold" {
  name        = "${local.glue_aparcamientos_prefix}-silver-to-gold"
  description = "Silver -> Gold de aparcamientos rotacionales: ocupacion media por aparcamiento y hora (tarea 048)."

  role_arn          = aws_iam_role.glue_aparcamientos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aparcamientos_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aparcamientos_por_parking_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aparcamientos]
}

# Jobs de un solo uso (tarea 075) para reconstruir Silver/Gold de `aparcamientos`
# desde cero, deduplicado -- ver docstring de `glue_backfill_dedup.py`. Sin
# trigger ni schedule: se lanzan a mano, una vez.
resource "aws_s3_object" "glue_script_aparcamientos_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aparcamientos_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup.py")
}

resource "aws_glue_job" "aparcamientos_silver_backfill_dedup" {
  name        = "${local.glue_aparcamientos_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion deduplicada de Silver de aparcamientos desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_aparcamientos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aparcamientos_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aparcamientos/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/aparcamientos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aparcamientos]
}

resource "aws_s3_object" "glue_script_aparcamientos_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aparcamientos_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aparcamientos/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "aparcamientos_gold_backfill_dedup" {
  name        = "${local.glue_aparcamientos_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion completa de Gold de aparcamientos desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_aparcamientos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aparcamientos_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aparcamientos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aparcamientos_por_parking_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aparcamientos]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (Glue, tarea 041/046/047/048 extendido a un QUINTO
# dataset (`calidad_aire`, lecturas horarias de la red de estaciones de
# calidad del aire de Madrid, ver doc/006,
# `ingesta/capturas/calidad_aire_madrid.py` y
# `procesamiento/silver_gold/calidad_aire/`). Alcance de ESTA tarea: igual
# que la 041/046/047/048, solo código/infraestructura, sin `terraform apply`
# -- `terraform plan`/`apply` de este bloque quedan para una tarea posterior
# con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/calidad_aire/*`, `silver/calidad_aire/*`,
# `gold/calidad_aire_por_estacion_contaminante_hora/*`) -- no se comparte
# ningún rol con `trafico`/`transporte_publico_emt`/`bicimad`/
# `aparcamientos`, mismo principio de mínimo privilegio por dataset que ya
# aplicaba `ingesta` (ver `procesamiento/README.md`).
# ---------------------------------------------------------------------------

locals {
  glue_calidad_aire_prefix = "${var.project_name}-${var.environment}-calidad-aire"
}

resource "aws_s3_object" "glue_script_calidad_aire_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/calidad_aire_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_calidad_aire_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/calidad_aire_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_calidad_aire_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_calidad_aire" {
  name = "${local.glue_calidad_aire_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de calidad del aire (tarea 049)."
  assume_role_policy = data.aws_iam_policy_document.glue_calidad_aire_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_calidad_aire_service_role" {
  role       = aws_iam_role.glue_calidad_aire.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_calidad_aire_data_access" {
  statement {
    sid    = "ReadBronzeCalidadAire"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/calidad_aire/*"]
  }

  statement {
    sid    = "ReadWriteSilverCalidadAire"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/calidad_aire/*"]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsCalidadAire"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/calidad_aire/*"]
  }

  statement {
    sid    = "WriteGoldCalidadAirePorEstacionContaminanteHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/calidad_aire_por_estacion_contaminante_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/calidad_aire_por_estacion_contaminante_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForCalidadAirePrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "calidad_aire/*",
        "calidad_aire_por_estacion_contaminante_hora/*",
        "_quality_reports/calidad_aire/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets
  # -- no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogCalidadAireTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_calidad_aire_data_access" {
  name = "${local.glue_calidad_aire_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de calidad del aire a los buckets del lakehouse y al catalogo de Glue (tarea 049)."
  policy      = data.aws_iam_policy_document.glue_calidad_aire_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_calidad_aire_data_access" {
  role       = aws_iam_role.glue_calidad_aire.name
  policy_arn = aws_iam_policy.glue_calidad_aire_data_access.arn
}

resource "aws_glue_catalog_table" "calidad_aire_silver" {
  name          = "calidad_aire"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Lecturas de calidad del aire de la red de estaciones de Madrid, limpias/validadas (tarea 049)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "station_address"
      type = "string"
    }
    columns {
      name = "magnitude_code"
      type = "string"
    }
    columns {
      name = "pollutant"
      type = "string"
    }
    columns {
      name = "pollutant_name"
      type = "string"
    }
    columns {
      name = "unit"
      type = "string"
    }
    columns {
      name = "value"
      type = "double"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string>"
    }
  }
}

resource "aws_glue_catalog_table" "calidad_aire_gold" {
  name          = "calidad_aire_por_estacion_contaminante_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Calidad del aire agregada por estación, contaminante y hora (tarea 049)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/calidad_aire_por_estacion_contaminante_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/calidad_aire_por_estacion_contaminante_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "magnitude_code"
      type = "string"
    }
    columns {
      name = "pollutant"
      type = "string"
    }
    columns {
      name = "pollutant_name"
      type = "string"
    }
    columns {
      name = "unit"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "avg_value"
      type = "double"
    }
    columns {
      name = "max_value"
      type = "double"
    }
    columns {
      name = "min_value"
      type = "double"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_calidad_aire" {
  name              = "/aws-glue/jobs/${local.glue_calidad_aire_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "calidad_aire_bronze_to_silver" {
  name        = "${local.glue_calidad_aire_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de calidad del aire: normalizacion, puerta de calidad por contaminante (tarea 049)."

  role_arn          = aws_iam_role.glue_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_calidad_aire_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/calidad_aire/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/calidad_aire/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_calidad_aire]
}

resource "aws_glue_job" "calidad_aire_silver_to_gold" {
  name        = "${local.glue_calidad_aire_prefix}-silver-to-gold"
  description = "Silver -> Gold de calidad del aire: valor medio/max/min por estacion, contaminante y hora (tarea 049)."

  role_arn          = aws_iam_role.glue_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_calidad_aire_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/calidad_aire_por_estacion_contaminante_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_calidad_aire]
}

# Jobs de un solo uso (tarea 075) para reconstruir Silver/Gold de `calidad_aire`
# desde cero, deduplicado -- ver docstring de `glue_backfill_dedup.py`. Sin
# trigger ni schedule: se lanzan a mano, una vez.
resource "aws_s3_object" "glue_script_calidad_aire_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/calidad_aire_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup.py")
}

resource "aws_glue_job" "calidad_aire_silver_backfill_dedup" {
  name        = "${local.glue_calidad_aire_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion deduplicada de Silver de calidad_aire desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_calidad_aire_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/calidad_aire/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/calidad_aire/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_calidad_aire]
}

resource "aws_s3_object" "glue_script_calidad_aire_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/calidad_aire_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/calidad_aire/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "calidad_aire_gold_backfill_dedup" {
  name        = "${local.glue_calidad_aire_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion completa de Gold de calidad_aire desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_calidad_aire_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/calidad_aire/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/calidad_aire_por_estacion_contaminante_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_calidad_aire]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (Glue, tarea 041/046/047/048/049 extendido a un
# SEXTO dataset (`meteorologia`, lecturas horarias de la red de estaciones
# meteorológicas de Madrid, ver doc/008,
# `ingesta/capturas/meteorologia_madrid.py` y
# `procesamiento/silver_gold/meteorologia/`). Alcance de ESTA tarea: igual
# que la 041/046/047/048/049, solo código/infraestructura, sin `terraform
# apply` -- `terraform plan`/`apply` de este bloque quedan para una tarea
# posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/meteorologia/*`, `silver/meteorologia/*`,
# `gold/meteorologia_por_estacion_magnitud_hora/*`) -- no se comparte ningún
# rol con `trafico`/`transporte_publico_emt`/`bicimad`/`aparcamientos`/
# `calidad_aire`, mismo principio de mínimo privilegio por dataset que ya
# aplicaba `ingesta` (ver `procesamiento/README.md`).
# ---------------------------------------------------------------------------

locals {
  glue_meteorologia_prefix = "${var.project_name}-${var.environment}-meteorologia"
}

resource "aws_s3_object" "glue_script_meteorologia_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/meteorologia_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_meteorologia_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/meteorologia_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_meteorologia_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_meteorologia" {
  name = "${local.glue_meteorologia_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de meteorología (tarea 050)."
  assume_role_policy = data.aws_iam_policy_document.glue_meteorologia_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_meteorologia_service_role" {
  role       = aws_iam_role.glue_meteorologia.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_meteorologia_data_access" {
  statement {
    sid    = "ReadBronzeMeteorologia"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/meteorologia/*"]
  }

  statement {
    sid    = "ReadWriteSilverMeteorologia"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/meteorologia/*"]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsMeteorologia"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/meteorologia/*"]
  }

  statement {
    sid    = "WriteGoldMeteorologiaPorEstacionMagnitudHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/meteorologia_por_estacion_magnitud_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/meteorologia_por_estacion_magnitud_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForMeteorologiaPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "meteorologia/*",
        "meteorologia_por_estacion_magnitud_hora/*",
        "_quality_reports/meteorologia/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets
  # -- no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogMeteorologiaTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_meteorologia_data_access" {
  name = "${local.glue_meteorologia_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de meteorologia a los buckets del lakehouse y al catalogo de Glue (tarea 050)."
  policy      = data.aws_iam_policy_document.glue_meteorologia_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_meteorologia_data_access" {
  role       = aws_iam_role.glue_meteorologia.name
  policy_arn = aws_iam_policy.glue_meteorologia_data_access.arn
}

resource "aws_glue_catalog_table" "meteorologia_silver" {
  name          = "meteorologia"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Lecturas meteorológicas de la red de estaciones de Madrid, limpias/validadas y pivotadas a formato largo (tarea 050)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "station_address"
      type = "string"
    }
    columns {
      name = "magnitude"
      type = "string"
    }
    columns {
      name = "value"
      type = "double"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string,altitude_m:int>"
    }
  }
}

resource "aws_glue_catalog_table" "meteorologia_gold" {
  name          = "meteorologia_por_estacion_magnitud_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Meteorología agregada por estación, magnitud y hora (tarea 050)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/meteorologia_por_estacion_magnitud_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/meteorologia_por_estacion_magnitud_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "magnitude"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "avg_value"
      type = "double"
    }
    columns {
      name = "max_value"
      type = "double"
    }
    columns {
      name = "min_value"
      type = "double"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "altitude_m"
      type = "int"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_meteorologia" {
  name              = "/aws-glue/jobs/${local.glue_meteorologia_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "meteorologia_bronze_to_silver" {
  name        = "${local.glue_meteorologia_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de meteorologia: pivote ancho->largo, puerta de calidad por magnitud (tarea 050)."

  role_arn          = aws_iam_role.glue_meteorologia.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_meteorologia_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/meteorologia/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/meteorologia/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_meteorologia]
}

resource "aws_glue_job" "meteorologia_silver_to_gold" {
  name        = "${local.glue_meteorologia_prefix}-silver-to-gold"
  description = "Silver -> Gold de meteorologia: valor medio/max/min por estacion, magnitud y hora (tarea 050)."

  role_arn          = aws_iam_role.glue_meteorologia.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_meteorologia_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/meteorologia_por_estacion_magnitud_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_meteorologia]
}

# Jobs de un solo uso (tarea 075) para reconstruir Silver/Gold de `meteorologia`
# desde cero, deduplicado -- ver docstring de `glue_backfill_dedup.py`. Sin
# trigger ni schedule: se lanzan a mano, una vez.
resource "aws_s3_object" "glue_script_meteorologia_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/meteorologia_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup.py")
}

resource "aws_glue_job" "meteorologia_silver_backfill_dedup" {
  name        = "${local.glue_meteorologia_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion deduplicada de Silver de meteorologia desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_meteorologia.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_meteorologia_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/meteorologia/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/meteorologia/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_meteorologia]
}

resource "aws_s3_object" "glue_script_meteorologia_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/meteorologia_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/meteorologia/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "meteorologia_gold_backfill_dedup" {
  name        = "${local.glue_meteorologia_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 075): reconstruccion completa de Gold de meteorologia desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_meteorologia.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_meteorologia_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/meteorologia/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/meteorologia_por_estacion_magnitud_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_meteorologia]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050 extendido a un
# SEPTIMO dataset (`ruido`, contaminación acústica diaria de la Red Fija del
# SIVCA de Madrid, ver doc/008, `ingesta/capturas/ruido_madrid.py` y
# `procesamiento/silver_gold/ruido/`). Alcance de ESTA tarea: igual que las
# anteriores, solo código/infraestructura, sin `terraform apply` -- `terraform
# plan`/`apply` de este bloque quedan para una tarea posterior con revisión
# de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/ruido/*`, `silver/ruido/*`,
# `gold/ruido_por_estacion_periodo_fecha/*`) -- no se comparte ningún rol con
# el resto de datasets, mismo principio de mínimo privilegio por dataset que
# ya aplicaba `ingesta` (ver `procesamiento/README.md`).
#
# Diferencia real frente al resto: esta fuente es diaria por estación+periodo
# (no horaria), así que Silver se particiona solo por `fecha` (sin `hora`) --
# ver `procesamiento/silver_gold/ruido/transform.py`.
# ---------------------------------------------------------------------------

locals {
  glue_ruido_prefix = "${var.project_name}-${var.environment}-ruido"
}

resource "aws_s3_object" "glue_script_ruido_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/ruido_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/ruido/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_ruido_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/ruido_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/ruido/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_ruido_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_ruido" {
  name = "${local.glue_ruido_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de contaminación acústica (tarea 053)."
  assume_role_policy = data.aws_iam_policy_document.glue_ruido_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_ruido_service_role" {
  role       = aws_iam_role.glue_ruido.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_ruido_data_access" {
  statement {
    sid    = "ReadBronzeRuido"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/ruido/*"]
  }

  statement {
    sid    = "ReadWriteSilverRuido"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052)
    # y en el statement de Gold de este mismo fichero: el marcador
    # `_$folder$` que crea el committer de Spark cuando el DataFrame de
    # Silver sale vacío (hueco detectado por la tarea 061 para
    # `cartelera_cines_estrenos`/`afluencia_lugares`, corregido aquí en
    # todos los datasets del segundo lote antes de que llegue a fallar).
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/ruido/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/ruido_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsRuido"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/ruido/*"]
  }

  statement {
    sid    = "WriteGoldRuidoPorEstacionPeriodoFecha"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/ruido_por_estacion_periodo_fecha/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/ruido_por_estacion_periodo_fecha_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForRuidoPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "ruido/*",
        "ruido_por_estacion_periodo_fecha/*",
        "_quality_reports/ruido/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogRuidoTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_ruido_data_access" {
  name = "${local.glue_ruido_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de contaminación acústica a los buckets del lakehouse y al catalogo de Glue (tarea 053)."
  policy      = data.aws_iam_policy_document.glue_ruido_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_ruido_data_access" {
  role       = aws_iam_role.glue_ruido.name
  policy_arn = aws_iam_policy.glue_ruido_data_access.arn
}

resource "aws_glue_catalog_table" "ruido_silver" {
  name          = "ruido"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Lecturas diarias de contaminación acústica de la Red Fija del SIVCA de Madrid, limpias/validadas (tarea 053)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/fecha=$${fecha}/"
  }

  # Solo `fecha` -- a diferencia del resto del patrón, esta fuente es diaria
  # (sin hora), ver `procesamiento/silver_gold/ruido/transform.py`.
  partition_keys {
    name = "fecha"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "station_address"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "neighbourhood"
      type = "string"
    }
    columns {
      name = "period"
      type = "string"
    }
    columns {
      name = "period_name"
      type = "string"
    }
    columns {
      name = "measured_date"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "laeq_db"
      type = "double"
    }
    columns {
      name = "l1_db"
      type = "double"
    }
    columns {
      name = "l10_db"
      type = "double"
    }
    columns {
      name = "l50_db"
      type = "double"
    }
    columns {
      name = "l90_db"
      type = "double"
    }
    columns {
      name = "l99_db"
      type = "double"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string,altitude_m:int>"
    }
  }
}

resource "aws_glue_catalog_table" "ruido_gold" {
  name          = "ruido_por_estacion_periodo_fecha"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Contaminación acústica agregada por estación, periodo horario y día, con media móvil de 7 días de LAeq (tarea 053)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/ruido_por_estacion_periodo_fecha/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/ruido_por_estacion_periodo_fecha/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "station_name"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "neighbourhood"
      type = "string"
    }
    columns {
      name = "period"
      type = "string"
    }
    columns {
      name = "period_name"
      type = "string"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "avg_laeq_db"
      type = "double"
    }
    columns {
      name = "max_laeq_db"
      type = "double"
    }
    columns {
      name = "min_laeq_db"
      type = "double"
    }
    columns {
      name = "avg_l1_db"
      type = "double"
    }
    columns {
      name = "avg_l10_db"
      type = "double"
    }
    columns {
      name = "avg_l50_db"
      type = "double"
    }
    columns {
      name = "avg_l90_db"
      type = "double"
    }
    columns {
      name = "avg_l99_db"
      type = "double"
    }
    columns {
      name = "laeq_rolling_7d_avg_db"
      type = "double"
    }
    columns {
      name = "laeq_rolling_7d_days"
      type = "bigint"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "altitude_m"
      type = "int"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_ruido" {
  name              = "/aws-glue/jobs/${local.glue_ruido_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "ruido_bronze_to_silver" {
  name        = "${local.glue_ruido_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de contaminación acústica: normalizacion, puerta de calidad por nivel sonoro (tarea 053)."

  role_arn          = aws_iam_role.glue_ruido.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_ruido_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/ruido/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/ruido/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_ruido]
}

resource "aws_glue_job" "ruido_silver_to_gold" {
  name        = "${local.glue_ruido_prefix}-silver-to-gold"
  description = "Silver -> Gold de contaminación acústica: resumen diario por estacion y periodo, con media movil de 7 dias de LAeq (tarea 053)."

  role_arn          = aws_iam_role.glue_ruido.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_ruido_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/ruido_por_estacion_periodo_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_ruido]
}

# Jobs de un solo uso (tarea 077) para reconstruir Silver/Gold de ruido
# deduplicados desde cero -- ver
# procesamiento/silver_gold/ruido/glue_backfill_dedup*.py.
resource "aws_s3_object" "glue_script_ruido_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/ruido_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup.py")
}

resource "aws_glue_job" "ruido_silver_backfill_dedup" {
  name        = "${local.glue_ruido_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion deduplicada de Silver de ruido desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_ruido.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_ruido_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/ruido/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/ruido/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_ruido]
}

resource "aws_s3_object" "glue_script_ruido_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/ruido_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/ruido/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "ruido_gold_backfill_dedup" {
  name        = "${local.glue_ruido_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion completa de Gold de ruido (incluida la media movil de 7 dias sobre el historico completo) desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_ruido.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_ruido_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/ruido/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/ruido_por_estacion_periodo_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_ruido]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050/053 extendido a un
# OCTAVO dataset (`aforos_peatones_bicicletas`, conteos horarios de la red de
# estaciones permanentes de aforo de peatones y bicicletas de Madrid, ver
# doc/0XX (aforos), `ingesta/capturas/aforos_peatones_bicicletas_madrid.py` y
# `procesamiento/silver_gold/aforos_peatones_bicicletas/`). Alcance de ESTA
# tarea: igual que las anteriores, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para
# una tarea posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/aforos_peatones_bicicletas/*`,
# `silver/aforos_peatones_bicicletas/*`,
# `gold/aforos_peatones_bicicletas_por_estacion_modo_hora/*`) -- no se
# comparte ningún rol con el resto de datasets, mismo principio de mínimo
# privilegio por dataset que ya aplicaba `ingesta`.
#
# Incluye desde el principio los dos statements de permisos que las tareas
# 051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
# los seis primeros datasets (`WriteSilverQualityReports...` y el marcador
# `_$folder$` de Gold), mismo criterio ya aplicado por `ruido` (tarea 053).
# ---------------------------------------------------------------------------

locals {
  glue_aforos_peatones_bicicletas_prefix = "${var.project_name}-${var.environment}-aforos-peatones-bicicletas"
}

resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_aforos_peatones_bicicletas_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_aforos_peatones_bicicletas" {
  name = "${local.glue_aforos_peatones_bicicletas_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de aforos de peatones y bicicletas (tarea 054)."
  assume_role_policy = data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_aforos_peatones_bicicletas_service_role" {
  role       = aws_iam_role.glue_aforos_peatones_bicicletas.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_aforos_peatones_bicicletas_data_access" {
  statement {
    sid    = "ReadBronzeAforosPeatonesBicicletas"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/aforos_peatones_bicicletas/*"]
  }

  statement {
    sid    = "ReadWriteSilverAforosPeatonesBicicletas"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en el statement de Silver de `ruido`
    # (tarea 061): marcador `_$folder$` para cuando el DataFrame de Silver
    # sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/aforos_peatones_bicicletas/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/aforos_peatones_bicicletas_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsAforosPeatonesBicicletas"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/aforos_peatones_bicicletas/*"]
  }

  statement {
    sid    = "WriteGoldAforosPeatonesBicicletasPorEstacionModoHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/aforos_peatones_bicicletas_por_estacion_modo_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/aforos_peatones_bicicletas_por_estacion_modo_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForAforosPeatonesBicicletasPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "aforos_peatones_bicicletas/*",
        "aforos_peatones_bicicletas_por_estacion_modo_hora/*",
        "_quality_reports/aforos_peatones_bicicletas/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogAforosPeatonesBicicletasTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_aforos_peatones_bicicletas_data_access" {
  name = "${local.glue_aforos_peatones_bicicletas_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de aforos de peatones y bicicletas a los buckets del lakehouse y al catalogo de Glue (tarea 054)."
  policy      = data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_aforos_peatones_bicicletas_data_access" {
  role       = aws_iam_role.glue_aforos_peatones_bicicletas.name
  policy_arn = aws_iam_policy.glue_aforos_peatones_bicicletas_data_access.arn
}

resource "aws_glue_catalog_table" "aforos_peatones_bicicletas_silver" {
  name          = "aforos_peatones_bicicletas"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Conteos horarios de peatones y bicicletas de la red de estaciones permanentes de aforo de Madrid, limpios/validados (tarea 054)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification          = "parquet"
    "parquet.compression"   = "SNAPPY"
    "projection.enabled"    = "true"
    "projection.fecha.type" = "date"
    # `measured_at` real de esta fuente (madrid_aforos_peatones_bicicletas)
    # trae fecha 2024-06-30 (ver doc/087) -- muy fuera de "2026-08-01,
    # NOW+1DAY" (el rango que si vale para el resto de datasets, cuyo
    # `measured_at` es casi en tiempo real). Con ese rango estrecho, Athena
    # calcula por formula que esa particion no existe y no la lee, aunque el
    # fichero Parquet este realmente en S3. Se amplia a partir de 2024-01-01
    # para cubrir el historico real de este dataset en concreto, sin tocar
    # el resto de tablas.
    "projection.fecha.range"         = "2024-01-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }
  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "mode"
      type = "string"
    }
    columns {
      name = "count"
      type = "int"
    }
    columns {
      name = "measured_at"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
    columns {
      name = "district_code"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "address_notes"
      type = "string"
    }
    columns {
      name = "location"
      type = "struct<lat:double,lon:double,srid:string>"
    }
  }
}

resource "aws_glue_catalog_table" "aforos_peatones_bicicletas_gold" {
  name          = "aforos_peatones_bicicletas_por_estacion_modo_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Conteo total/medio de peatones y bicicletas agregado por estación, modo y hora (tarea 054)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification         = "parquet"
    "parquet.compression"  = "SNAPPY"
    "projection.enabled"   = "true"
    "projection.date.type" = "date"
    # Mismo hallazgo que en la tabla Silver de arriba (ver doc/087): la fecha
    # (`date`, derivada de `measured_at`) de este dataset en concreto es
    # 2024-06-30, no la fecha de ingestion -- se amplia el rango para que
    # Athena pueda ver esa particion real.
    "projection.date.range"         = "2024-01-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aforos_peatones_bicicletas_por_estacion_modo_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aforos_peatones_bicicletas_por_estacion_modo_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "station_id"
      type = "string"
    }
    columns {
      name = "mode"
      type = "string"
    }
    columns {
      name = "district_code"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "address_notes"
      type = "string"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "first_measured_at"
      type = "string"
    }
    columns {
      name = "last_measured_at"
      type = "string"
    }
    columns {
      name = "total_count"
      type = "bigint"
    }
    columns {
      name = "avg_count"
      type = "double"
    }
    columns {
      name = "max_count"
      type = "int"
    }
    columns {
      name = "min_count"
      type = "int"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_aforos_peatones_bicicletas" {
  name              = "/aws-glue/jobs/${local.glue_aforos_peatones_bicicletas_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "aforos_peatones_bicicletas_bronze_to_silver" {
  name        = "${local.glue_aforos_peatones_bicicletas_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de aforos de peatones y bicicletas: normalizacion, puerta de calidad por conteo (tarea 054)."

  role_arn          = aws_iam_role.glue_aforos_peatones_bicicletas.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aforos_peatones_bicicletas_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aforos_peatones_bicicletas/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/aforos_peatones_bicicletas/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas]
}

resource "aws_glue_job" "aforos_peatones_bicicletas_silver_to_gold" {
  name        = "${local.glue_aforos_peatones_bicicletas_prefix}-silver-to-gold"
  description = "Silver -> Gold de aforos de peatones y bicicletas: conteo total/medio por estacion, modo y hora (tarea 054)."

  role_arn          = aws_iam_role.glue_aforos_peatones_bicicletas.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aforos_peatones_bicicletas_por_estacion_modo_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas]
}

# Jobs de un solo uso (tarea 077) para reconstruir Silver/Gold de
# aforos_peatones_bicicletas deduplicados desde cero -- ver
# procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup*.py.
resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup.py")
}

resource "aws_glue_job" "aforos_peatones_bicicletas_silver_backfill_dedup" {
  name        = "${local.glue_aforos_peatones_bicicletas_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion deduplicada de Silver de aforos_peatones_bicicletas desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_aforos_peatones_bicicletas.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aforos_peatones_bicicletas/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/aforos_peatones_bicicletas/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas]
}

resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aforos_peatones_bicicletas/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "aforos_peatones_bicicletas_gold_backfill_dedup" {
  name        = "${local.glue_aforos_peatones_bicicletas_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion completa de Gold de aforos_peatones_bicicletas desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_aforos_peatones_bicicletas.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aforos_peatones_bicicletas/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aforos_peatones_bicicletas_por_estacion_modo_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050/053/054 extendido a
# un NOVENO dataset (`cartelera_cines_estrenos`, cartelera y horarios de
# cines de Madrid vía SensaCine, ver doc/023,
# `ingesta/capturas/cartelera_cines_madrid.py` y
# `procesamiento/silver_gold/cartelera_cines_estrenos/`). Alcance de ESTA
# tarea: igual que las anteriores, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para
# una tarea posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/cartelera_cines_estrenos/*`,
# `silver/cartelera_cines_estrenos/*`,
# `gold/cartelera_cines_estrenos_por_pelicula_cine_fecha/*`) -- no se
# comparte ningún rol con el resto de datasets, mismo principio de mínimo
# privilegio por dataset que ya aplicaba `ingesta`.
#
# Incluye desde el principio los dos statements de permisos que las tareas
# 051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
# los seis primeros datasets (`WriteSilverQualityReports...` y el marcador
# `_$folder$` de Gold), mismo criterio ya aplicado por `ruido`/
# `aforos_peatones_bicicletas` (tareas 053/054).
# ---------------------------------------------------------------------------

locals {
  glue_cartelera_cines_estrenos_prefix = "${var.project_name}-${var.environment}-cartelera-cines-estrenos"
}

resource "aws_s3_object" "glue_script_cartelera_cines_estrenos_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cartelera_cines_estrenos_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_cartelera_cines_estrenos_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cartelera_cines_estrenos_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cartelera_cines_estrenos/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_cartelera_cines_estrenos_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_cartelera_cines_estrenos" {
  name = "${local.glue_cartelera_cines_estrenos_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de cartelera de cines (tarea 055)."
  assume_role_policy = data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_cartelera_cines_estrenos_service_role" {
  role       = aws_iam_role.glue_cartelera_cines_estrenos.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_cartelera_cines_estrenos_data_access" {
  statement {
    sid    = "ReadBronzeCarteleraCinesEstrenos"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/cartelera_cines_estrenos/*"]
  }

  statement {
    sid    = "ReadWriteSilverCarteleraCinesEstrenos"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Hueco de permisos detectado por el job de sanidad de la tarea 061:
    # falta el marcador `_$folder$` que crea el committer de Spark cuando
    # el DataFrame de Silver sale vacío (mismo problema que ya se corrigió
    # a nivel Gold en la tarea 051, ver comentario del statement de Gold
    # de este mismo fichero).
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/cartelera_cines_estrenos/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/cartelera_cines_estrenos_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsCarteleraCinesEstrenos"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/cartelera_cines_estrenos/*"]
  }

  statement {
    sid    = "WriteGoldCarteleraCinesEstrenosPorPeliculaCineFecha"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/cartelera_cines_estrenos_por_pelicula_cine_fecha/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/cartelera_cines_estrenos_por_pelicula_cine_fecha_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForCarteleraCinesEstrenosPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "cartelera_cines_estrenos/*",
        "cartelera_cines_estrenos_por_pelicula_cine_fecha/*",
        "_quality_reports/cartelera_cines_estrenos/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogCarteleraCinesEstrenosTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_cartelera_cines_estrenos_data_access" {
  name = "${local.glue_cartelera_cines_estrenos_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de cartelera de cines a los buckets del lakehouse y al catalogo de Glue (tarea 055)."
  policy      = data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_cartelera_cines_estrenos_data_access" {
  role       = aws_iam_role.glue_cartelera_cines_estrenos.name
  policy_arn = aws_iam_policy.glue_cartelera_cines_estrenos_data_access.arn
}

resource "aws_glue_catalog_table" "cartelera_cines_estrenos_silver" {
  name          = "cartelera_cines_estrenos"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Sesiones de cine (pelicula, cine, horario) de la cartelera de Madrid, limpias/validadas (tarea 055)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cartelera_cines_estrenos/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }
  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cartelera_cines_estrenos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "cinema_id"
      type = "string"
    }
    columns {
      name = "chain"
      type = "string"
    }
    columns {
      name = "cinema_name"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "postal_code"
      type = "string"
    }
    columns {
      name = "locality"
      type = "string"
    }
    columns {
      name = "screen_count"
      type = "int"
    }
    columns {
      name = "movie_title"
      type = "string"
    }
    columns {
      name = "movie_url"
      type = "string"
    }
    columns {
      name = "language_version"
      type = "string"
    }
    columns {
      name = "experiences"
      type = "array<string>"
    }
    columns {
      name = "showtime_datetime"
      type = "string"
    }
    columns {
      name = "showtime_id"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "cartelera_cines_estrenos_gold" {
  name          = "cartelera_cines_estrenos_por_pelicula_cine_fecha"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Numero de sesiones de cine agregado por pelicula, cine y dia (tarea 055)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cartelera_cines_estrenos_por_pelicula_cine_fecha/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cartelera_cines_estrenos_por_pelicula_cine_fecha/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "movie_url"
      type = "string"
    }
    columns {
      name = "cinema_id"
      type = "string"
    }
    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "movie_title"
      type = "string"
    }
    columns {
      name = "chain"
      type = "string"
    }
    columns {
      name = "cinema_name"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "postal_code"
      type = "string"
    }
    columns {
      name = "locality"
      type = "string"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "sessions_count"
      type = "bigint"
    }
    columns {
      name = "first_showtime_datetime"
      type = "string"
    }
    columns {
      name = "last_showtime_datetime"
      type = "string"
    }
    columns {
      name = "language_versions"
      type = "array<string>"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_cartelera_cines_estrenos" {
  name              = "/aws-glue/jobs/${local.glue_cartelera_cines_estrenos_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "cartelera_cines_estrenos_bronze_to_silver" {
  name        = "${local.glue_cartelera_cines_estrenos_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de cartelera de cines: normalizacion, puerta de calidad por sesion (tarea 055)."

  role_arn          = aws_iam_role.glue_cartelera_cines_estrenos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cartelera_cines_estrenos_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/cartelera_cines_estrenos/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cartelera_cines_estrenos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/cartelera_cines_estrenos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cartelera_cines_estrenos]
}

resource "aws_glue_job" "cartelera_cines_estrenos_silver_to_gold" {
  name        = "${local.glue_cartelera_cines_estrenos_prefix}-silver-to-gold"
  description = "Silver -> Gold de cartelera de cines: numero de sesiones por pelicula, cine y dia (tarea 055)."

  role_arn          = aws_iam_role.glue_cartelera_cines_estrenos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cartelera_cines_estrenos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cartelera_cines_estrenos_por_pelicula_cine_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cartelera_cines_estrenos]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050/053/054/055
# extendido a un DÉCIMO dataset (`agenda_eventos`, agenda de eventos
# culturales y de ocio de Madrid -- dos fuentes combinadas, dataset
# municipal de datos.madrid.es y agenda turística de esmadrid.com -- ver
# `ingesta/capturas/agenda_eventos_madrid.py` y
# `procesamiento/silver_gold/agenda_eventos/`). Alcance de ESTA tarea: igual
# que las anteriores, solo código/infraestructura, sin `terraform apply` --
# `terraform plan`/`apply` de este bloque quedan para una tarea posterior
# con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/agenda_eventos/*`, `silver/agenda_eventos/*`,
# `gold/agenda_eventos_por_categoria_distrito_fecha/*`) -- no se comparte
# ningún rol con el resto de datasets, mismo principio de mínimo privilegio
# por dataset que ya aplicaba `ingesta`.
#
# Incluye desde el principio los dos statements de permisos que las tareas
# 051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
# los seis primeros datasets (`WriteSilverQualityReports...` y el marcador
# `_$folder$` de Gold), mismo criterio ya aplicado por `ruido`/
# `aforos_peatones_bicicletas`/`cartelera_cines_estrenos` (tareas 053/054/055).
#
# La tabla Silver del catálogo declara una única `partition_keys` (`fecha`,
# sin `hora`) -- mismo motivo que `ruido` (tarea 053): una de las dos
# fuentes (`agenda_turismo_esmadrid`) no publica ninguna hora de
# celebración, ver docstring de `glue_bronze_to_silver.py`.
# ---------------------------------------------------------------------------

locals {
  glue_agenda_eventos_prefix = "${var.project_name}-${var.environment}-agenda-eventos"
}

resource "aws_s3_object" "glue_script_agenda_eventos_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/agenda_eventos_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_agenda_eventos_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/agenda_eventos_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_agenda_eventos_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_agenda_eventos" {
  name = "${local.glue_agenda_eventos_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de la agenda de eventos (tarea 056)."
  assume_role_policy = data.aws_iam_policy_document.glue_agenda_eventos_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_agenda_eventos_service_role" {
  role       = aws_iam_role.glue_agenda_eventos.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_agenda_eventos_data_access" {
  statement {
    sid    = "ReadBronzeAgendaEventos"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/agenda_eventos/*"]
  }

  statement {
    sid    = "ReadWriteSilverAgendaEventos"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en el statement de Silver de `ruido`
    # (tarea 061): marcador `_$folder$` para cuando el DataFrame de Silver
    # sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/agenda_eventos/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/agenda_eventos_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsAgendaEventos"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/agenda_eventos/*"]
  }

  statement {
    sid    = "WriteGoldAgendaEventosPorCategoriaDistritoFecha"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/agenda_eventos_por_categoria_distrito_fecha/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/agenda_eventos_por_categoria_distrito_fecha_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForAgendaEventosPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "agenda_eventos/*",
        "agenda_eventos_por_categoria_distrito_fecha/*",
        "_quality_reports/agenda_eventos/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogAgendaEventosTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_agenda_eventos_data_access" {
  name = "${local.glue_agenda_eventos_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de la agenda de eventos a los buckets del lakehouse y al catalogo de Glue (tarea 056)."
  policy      = data.aws_iam_policy_document.glue_agenda_eventos_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_agenda_eventos_data_access" {
  role       = aws_iam_role.glue_agenda_eventos.name
  policy_arn = aws_iam_policy.glue_agenda_eventos_data_access.arn
}

resource "aws_glue_catalog_table" "agenda_eventos_silver" {
  name          = "agenda_eventos"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Eventos culturales y de ocio de Madrid (agenda municipal + esMadrid), limpios/validados (tarea 056)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/fecha=$${fecha}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "title"
      type = "string"
    }
    columns {
      name = "description"
      type = "string"
    }
    columns {
      name = "category"
      type = "string"
    }
    columns {
      name = "start_datetime"
      type = "string"
    }
    columns {
      name = "end_datetime"
      type = "string"
    }
    columns {
      name = "schedule_text"
      type = "string"
    }
    columns {
      name = "free"
      type = "boolean"
    }
    columns {
      name = "price_info"
      type = "string"
    }
    columns {
      name = "venue_name"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "neighborhood"
      type = "string"
    }
    columns {
      name = "postal_code"
      type = "string"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "url"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "agenda_eventos_gold" {
  name          = "agenda_eventos_por_categoria_distrito_fecha"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Numero de eventos culturales/de ocio agregado por categoria, distrito y dia de celebracion (tarea 056)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/agenda_eventos_por_categoria_distrito_fecha/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/agenda_eventos_por_categoria_distrito_fecha/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "category"
      type = "string"
    }
    columns {
      name = "district"
      type = "string"
    }
    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "events_count"
      type = "bigint"
    }
    columns {
      name = "free_events_count"
      type = "bigint"
    }
    columns {
      name = "sources"
      type = "array<string>"
    }
    columns {
      name = "first_start_datetime"
      type = "string"
    }
    columns {
      name = "last_start_datetime"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_agenda_eventos" {
  name              = "/aws-glue/jobs/${local.glue_agenda_eventos_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "agenda_eventos_bronze_to_silver" {
  name        = "${local.glue_agenda_eventos_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de la agenda de eventos: normalizacion, puerta de calidad por evento (tarea 056)."

  role_arn          = aws_iam_role.glue_agenda_eventos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_agenda_eventos_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/agenda_eventos/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/agenda_eventos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_agenda_eventos]
}

resource "aws_glue_job" "agenda_eventos_silver_to_gold" {
  name        = "${local.glue_agenda_eventos_prefix}-silver-to-gold"
  description = "Silver -> Gold de la agenda de eventos: numero de eventos por categoria, distrito y dia (tarea 056)."

  role_arn          = aws_iam_role.glue_agenda_eventos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_agenda_eventos_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/agenda_eventos_por_categoria_distrito_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_agenda_eventos]
}

# Jobs de un solo uso (tarea 077) para reconstruir Silver/Gold de
# agenda_eventos deduplicados desde cero -- ver
# procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup*.py.
resource "aws_s3_object" "glue_script_agenda_eventos_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/agenda_eventos_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup.py")
}

resource "aws_glue_job" "agenda_eventos_silver_backfill_dedup" {
  name        = "${local.glue_agenda_eventos_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion deduplicada de Silver de agenda_eventos desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_agenda_eventos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  # Timeout mas alto que el resto de jobs (var.glue_job_timeout_minutes,
  # 30 min): este job lee TODO el historico de Bronze de una vez.
  timeout     = 90
  max_retries = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_agenda_eventos_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/agenda_eventos/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/agenda_eventos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_agenda_eventos]
}

resource "aws_s3_object" "glue_script_agenda_eventos_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/agenda_eventos_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/agenda_eventos/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "agenda_eventos_gold_backfill_dedup" {
  name        = "${local.glue_agenda_eventos_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion completa de Gold de agenda_eventos desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_agenda_eventos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_agenda_eventos_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/agenda_eventos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/agenda_eventos_por_categoria_distrito_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_agenda_eventos]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050/053/054/055/056
# extendido a un UNDÉCIMO dataset (`bluesky_menciones`, menciones públicas de
# lugares/distritos de Madrid en Bluesky -- dos modos combinados bajo un
# campo `mode`: búsqueda puntual por lugar y barrido programado por distrito
# -- ver `ingesta/capturas/bluesky_menciones_madrid.py` y
# `procesamiento/silver_gold/bluesky_menciones/`). Alcance de ESTA tarea:
# igual que las anteriores, solo código/infraestructura, sin `terraform
# apply` -- `terraform plan`/`apply` de este bloque quedan para una tarea
# posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/bluesky_menciones/*`, `silver/bluesky_menciones/*`,
# `gold/bluesky_menciones_por_termino_modo_hora/*`) -- no se comparte ningún
# rol con el resto de datasets, mismo principio de mínimo privilegio por
# dataset que ya aplicaba `ingesta`.
#
# Incluye desde el principio los dos statements de permisos que las tareas
# 051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
# los seis primeros datasets (`WriteSilverQualityReports...` y el marcador
# `_$folder$` de Gold), mismo criterio ya aplicado por el resto del patrón
# desde la tarea 053.
#
# La tabla Silver del catálogo declara dos `partition_keys` (`fecha`/`hora`,
# el patrón horario estándar): a diferencia de `ruido`/`agenda_eventos`
# (agregación solo diaria, porque su fuente no tiene resolución horaria
# real), cada post de Bluesky trae un `created_at` con resolución de
# segundos y el modo `distrito_sweep` está pensado para un productor
# programado cada hora, ver docstring de `aggregate.py`.
# ---------------------------------------------------------------------------

locals {
  glue_bluesky_menciones_prefix = "${var.project_name}-${var.environment}-bluesky-menciones"
}

resource "aws_s3_object" "glue_script_bluesky_menciones_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bluesky_menciones_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_bluesky_menciones_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bluesky_menciones_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_bluesky_menciones_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_bluesky_menciones" {
  name = "${local.glue_bluesky_menciones_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de las menciones de Bluesky (tarea 057)."
  assume_role_policy = data.aws_iam_policy_document.glue_bluesky_menciones_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_bluesky_menciones_service_role" {
  role       = aws_iam_role.glue_bluesky_menciones.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_bluesky_menciones_data_access" {
  statement {
    sid    = "ReadBronzeBlueskyMenciones"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/bluesky_menciones/*"]
  }

  statement {
    sid    = "ReadWriteSilverBlueskyMenciones"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en el statement de Silver de `ruido`
    # (tarea 061): marcador `_$folder$` para cuando el DataFrame de Silver
    # sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/bluesky_menciones/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/bluesky_menciones_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsBlueskyMenciones"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/bluesky_menciones/*"]
  }

  statement {
    sid    = "WriteGoldBlueskyMencionesPorTerminoModoHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/bluesky_menciones_por_termino_modo_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/bluesky_menciones_por_termino_modo_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForBlueskyMencionesPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "bluesky_menciones/*",
        "bluesky_menciones_por_termino_modo_hora/*",
        "_quality_reports/bluesky_menciones/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogBlueskyMencionesTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_bluesky_menciones_data_access" {
  name = "${local.glue_bluesky_menciones_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de las menciones de Bluesky a los buckets del lakehouse y al catalogo de Glue (tarea 057)."
  policy      = data.aws_iam_policy_document.glue_bluesky_menciones_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_bluesky_menciones_data_access" {
  role       = aws_iam_role.glue_bluesky_menciones.name
  policy_arn = aws_iam_policy.glue_bluesky_menciones_data_access.arn
}

resource "aws_glue_catalog_table" "bluesky_menciones_silver" {
  name          = "bluesky_menciones"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Menciones publicas de lugares/distritos de Madrid en Bluesky, limpias/validadas (tarea 057)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }
  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "mode"
      type = "string"
    }
    columns {
      name = "match_term"
      type = "string"
    }
    columns {
      name = "post_hash"
      type = "string"
    }
    columns {
      name = "text"
      type = "string"
    }
    columns {
      name = "lang"
      type = "string"
    }
    columns {
      name = "created_at"
      type = "string"
    }
    columns {
      name = "indexed_at"
      type = "string"
    }
    columns {
      name = "like_count"
      type = "int"
    }
    columns {
      name = "repost_count"
      type = "int"
    }
    columns {
      name = "reply_count"
      type = "int"
    }
    columns {
      name = "quote_count"
      type = "int"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "bluesky_menciones_gold" {
  name          = "bluesky_menciones_por_termino_modo_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Numero de menciones de Bluesky agregado por termino de busqueda (lugar/distrito/evento), modo y hora (tarea 057)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bluesky_menciones_por_termino_modo_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bluesky_menciones_por_termino_modo_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "mode"
      type = "string"
    }
    columns {
      name = "match_term"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "mentions_count"
      type = "bigint"
    }
    columns {
      name = "langs"
      type = "array<string>"
    }
    columns {
      name = "total_like_count"
      type = "bigint"
    }
    columns {
      name = "total_repost_count"
      type = "bigint"
    }
    columns {
      name = "total_reply_count"
      type = "bigint"
    }
    columns {
      name = "total_quote_count"
      type = "bigint"
    }
    columns {
      name = "first_created_at"
      type = "string"
    }
    columns {
      name = "last_created_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_bluesky_menciones" {
  name              = "/aws-glue/jobs/${local.glue_bluesky_menciones_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "bluesky_menciones_bronze_to_silver" {
  name        = "${local.glue_bluesky_menciones_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de las menciones de Bluesky: normalizacion, puerta de calidad y deduplicacion de duplicados exactos por lote (tarea 057)."

  role_arn          = aws_iam_role.glue_bluesky_menciones.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bluesky_menciones_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/bluesky_menciones/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/bluesky_menciones/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bluesky_menciones]
}

resource "aws_glue_job" "bluesky_menciones_silver_to_gold" {
  name        = "${local.glue_bluesky_menciones_prefix}-silver-to-gold"
  description = "Silver -> Gold de las menciones de Bluesky: numero de menciones por termino, modo y hora (tarea 057)."

  role_arn          = aws_iam_role.glue_bluesky_menciones.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bluesky_menciones_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bluesky_menciones_por_termino_modo_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bluesky_menciones]
}

# Jobs de un solo uso (tarea 077) para reconstruir Silver/Gold de
# bluesky_menciones deduplicados desde cero -- ver
# procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup*.py.
resource "aws_s3_object" "glue_script_bluesky_menciones_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bluesky_menciones_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup.py")
}

resource "aws_glue_job" "bluesky_menciones_silver_backfill_dedup" {
  name        = "${local.glue_bluesky_menciones_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion deduplicada de Silver de bluesky_menciones desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_bluesky_menciones.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bluesky_menciones_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/bluesky_menciones/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/bluesky_menciones/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bluesky_menciones]
}

resource "aws_s3_object" "glue_script_bluesky_menciones_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/bluesky_menciones_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/bluesky_menciones/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "bluesky_menciones_gold_backfill_dedup" {
  name        = "${local.glue_bluesky_menciones_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion completa de Gold de bluesky_menciones desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_bluesky_menciones.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_bluesky_menciones_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/bluesky_menciones/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/bluesky_menciones_por_termino_modo_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_bluesky_menciones]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (tarea 041/046/047/048/049/050/053/054/055/056/057
# extendido a un DUODÉCIMO dataset (`aemet_prevision_avisos`, previsión diaria
# y avisos meteorológicos de AEMET OpenData -- ver
# `ingesta/capturas/aemet_prevision_avisos.py` y
# `procesamiento/silver_gold/aemet_prevision_avisos/`). Alcance de ESTA
# tarea: igual que las anteriores, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para
# una tarea posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM.
#
# DESVIACIÓN DELIBERADA del prefijo único `aemet_prevision_avisos/*` que
# sugería el enunciado de esta tarea: `ingesta/capturas/aemet_prevision_avisos.py`
# ya fija, en producción, DOS nombres de dataset Bronze distintos
# (`DATASET_PREDICCION = "aemet_prevision"`, `DATASET_AVISOS = "aemet_avisos"`,
# usados tal cual por `BronzeWriter`/`lambda_handler`) -- son dos prefijos S3
# reales (`bronze/aemet_prevision/*`, `bronze/aemet_avisos/*`), no uno
# combinado. Un rol acotado al prefijo que sugería el enunciado no tendría
# permiso para leer ningún dato real. Silver mantiene la misma separación
# que Bronze ya tiene fijada (`silver/aemet_prevision/*`,
# `silver/aemet_avisos/*`); Gold usa nombres propios por agregación
# (`gold/aemet_prevision_por_municipio_leadtime/*`,
# `gold/aemet_avisos_por_zona_fecha_nivel/*`) -- ver docstring de
# `procesamiento/silver_gold/aemet_prevision_avisos/transform.py`,
# "Prefijos S3 reales de Bronze", para el razonamiento completo. Sí se
# comparte UN ÚNICO rol IAM y UN ÚNICO par de jobs de Glue (Bronze->Silver,
# Silver->Gold) entre las dos formas de dato -- "job de Glue x2" tal como
# pide el enunciado, no cuatro jobs -- porque comparten productor,
# credencial (`AEMET_API_KEY`) y cadencia real de scheduling (ver
# `ingesta/README.md`, "Cadencia real de publicación").
#
# Incluye desde el principio los dos statements de permisos que las tareas
# 051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
# los seis primeros datasets (`WriteSilverQualityReports...` y el marcador
# `_$folder$` de Gold, aquí uno por cada tabla Gold), mismo criterio ya
# aplicado por el resto del patrón desde la tarea 053.
#
# Las tablas Silver del catálogo declaran una única `partition_keys`
# (`fecha`, sin `hora`): la previsión es diaria (sin resolución horaria
# real, mismo criterio que `ruido`/`agenda_eventos`) y los avisos, aunque sí
# traen hora de inicio de vigencia, no tienen volumen suficiente para
# justificar una partición horaria adicional.
# ---------------------------------------------------------------------------

locals {
  glue_aemet_prevision_avisos_prefix = "${var.project_name}-${var.environment}-aemet-prevision-avisos"
}

resource "aws_s3_object" "glue_script_aemet_prevision_avisos_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aemet_prevision_avisos_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_aemet_prevision_avisos_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/aemet_prevision_avisos_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_aemet_prevision_avisos_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_aemet_prevision_avisos" {
  name = "${local.glue_aemet_prevision_avisos_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de la previsión y avisos de AEMET (tarea 058)."
  assume_role_policy = data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_aemet_prevision_avisos_service_role" {
  role       = aws_iam_role.glue_aemet_prevision_avisos.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_aemet_prevision_avisos_data_access" {
  statement {
    sid    = "ReadBronzeAemetPrevision"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/aemet_prevision/*"]
  }

  statement {
    sid    = "ReadBronzeAemetAvisos"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/aemet_avisos/*"]
  }

  statement {
    sid    = "ReadWriteSilverAemetPrevision"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en el statement de Silver de `ruido`
    # (tarea 061): marcador `_$folder$` para cuando el DataFrame de Silver
    # sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/aemet_prevision/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/aemet_prevision_$folder$",
    ]
  }

  statement {
    sid    = "ReadWriteSilverAemetAvisos"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/aemet_avisos/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/aemet_avisos_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051.
  statement {
    sid    = "WriteSilverQualityReportsAemetPrevisionAvisos"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/aemet_prevision_avisos/*"]
  }

  statement {
    sid    = "WriteGoldAemetPrevisionPorMunicipioLeadtime"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
    # el marcador `_$folder$` que crea el committer de Spark cuando el
    # DataFrame de Gold sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/aemet_prevision_por_municipio_leadtime/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/aemet_prevision_por_municipio_leadtime_$folder$",
    ]
  }

  statement {
    sid    = "WriteGoldAemetAvisosPorZonaFechaNivel"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/aemet_avisos_por_zona_fecha_nivel/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/aemet_avisos_por_zona_fecha_nivel_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForAemetPrevisionAvisosPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "aemet_prevision/*",
        "aemet_avisos/*",
        "aemet_prevision_por_municipio_leadtime/*",
        "aemet_avisos_por_zona_fecha_nivel/*",
        "_quality_reports/aemet_prevision_avisos/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets --
  # no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogAemetPrevisionAvisosTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_aemet_prevision_avisos_data_access" {
  name = "${local.glue_aemet_prevision_avisos_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de la prevision y avisos de AEMET a los buckets del lakehouse y al catalogo de Glue (tarea 058)."
  policy      = data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_aemet_prevision_avisos_data_access" {
  role       = aws_iam_role.glue_aemet_prevision_avisos.name
  policy_arn = aws_iam_policy.glue_aemet_prevision_avisos_data_access.arn
}

resource "aws_glue_catalog_table" "aemet_prevision_silver" {
  name          = "aemet_prevision"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Prevision diaria de AEMET por municipio, limpia/validada (tarea 058)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_prevision/fecha=$${fecha}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_prevision/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "municipio_code"
      type = "string"
    }
    columns {
      name = "municipio_name"
      type = "string"
    }
    columns {
      name = "province"
      type = "string"
    }
    columns {
      name = "elaborated_at"
      type = "string"
    }
    columns {
      name = "valid_date"
      type = "string"
    }
    columns {
      name = "sky_state"
      type = "string"
    }
    columns {
      name = "sky_state_code"
      type = "string"
    }
    columns {
      name = "precipitation_probability_pct"
      type = "double"
    }
    columns {
      name = "temperature_max_c"
      type = "double"
    }
    columns {
      name = "temperature_min_c"
      type = "double"
    }
    columns {
      name = "thermal_sensation_max_c"
      type = "double"
    }
    columns {
      name = "thermal_sensation_min_c"
      type = "double"
    }
    columns {
      name = "humidity_max_pct"
      type = "double"
    }
    columns {
      name = "humidity_min_pct"
      type = "double"
    }
    columns {
      name = "wind_direction"
      type = "string"
    }
    columns {
      name = "wind_speed_kmh"
      type = "double"
    }
    columns {
      name = "wind_gust_max_kmh"
      type = "double"
    }
    columns {
      name = "uv_max"
      type = "double"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "aemet_avisos_silver" {
  name          = "aemet_avisos"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Avisos meteorologicos vigentes de AEMET, limpios/validados (tarea 058)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_avisos/fecha=$${fecha}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_avisos/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "identifier"
      type = "string"
    }
    columns {
      name = "sent_at"
      type = "string"
    }
    columns {
      name = "zone"
      type = "string"
    }
    columns {
      name = "level"
      type = "string"
    }
    columns {
      name = "phenomenon"
      type = "string"
    }
    columns {
      name = "probability"
      type = "string"
    }
    columns {
      name = "severity"
      type = "string"
    }
    columns {
      name = "urgency"
      type = "string"
    }
    columns {
      name = "certainty"
      type = "string"
    }
    columns {
      name = "effective_from"
      type = "string"
    }
    columns {
      name = "effective_until"
      type = "string"
    }
    columns {
      name = "headline"
      type = "string"
    }
    columns {
      name = "description"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "aemet_prevision_gold" {
  name          = "aemet_prevision_por_municipio_leadtime"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Prevision de AEMET agregada por municipio y horizonte (leadtime en dias), valores medios/maximos (tarea 058)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                     = "parquet"
    "parquet.compression"              = "SNAPPY"
    "projection.enabled"               = "true"
    "projection.municipio_code.type"   = "enum"
    "projection.municipio_code.values" = "28079"
    "storage.location.template"        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_prevision_por_municipio_leadtime/municipio_code=$${municipio_code}/"
  }

  partition_keys {
    name = "municipio_code"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_prevision_por_municipio_leadtime/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "leadtime_days"
      type = "int"
    }
    columns {
      name = "municipio_name"
      type = "string"
    }
    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "avg_temperature_max_c"
      type = "double"
    }
    columns {
      name = "max_temperature_max_c"
      type = "double"
    }
    columns {
      name = "avg_temperature_min_c"
      type = "double"
    }
    columns {
      name = "min_temperature_min_c"
      type = "double"
    }
    columns {
      name = "avg_precipitation_probability_pct"
      type = "double"
    }
    columns {
      name = "max_precipitation_probability_pct"
      type = "double"
    }
    columns {
      name = "first_valid_date"
      type = "string"
    }
    columns {
      name = "last_valid_date"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "aemet_avisos_gold" {
  name          = "aemet_avisos_por_zona_fecha_nivel"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Numero de avisos meteorologicos activos de AEMET agregado por zona, dia de inicio de vigencia y nivel (tarea 058)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_avisos_por_zona_fecha_nivel/fecha=$${fecha}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_avisos_por_zona_fecha_nivel/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "zone"
      type = "string"
    }
    columns {
      name = "level"
      type = "string"
    }
    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "alerts_count"
      type = "bigint"
    }
    columns {
      name = "phenomena"
      type = "array<string>"
    }
    columns {
      name = "first_effective_from"
      type = "string"
    }
    columns {
      name = "last_effective_until"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_aemet_prevision_avisos" {
  name              = "/aws-glue/jobs/${local.glue_aemet_prevision_avisos_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "aemet_prevision_avisos_bronze_to_silver" {
  name        = "${local.glue_aemet_prevision_avisos_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de la prevision y avisos de AEMET: normalizacion y puerta de calidad de ambas formas de dato (tarea 058)."

  role_arn          = aws_iam_role.glue_aemet_prevision_avisos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aemet_prevision_avisos_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_prevision_path"            = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aemet_prevision/"
    "--bronze_avisos_path"               = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/aemet_avisos/"
    "--silver_prevision_path"            = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_prevision/"
    "--silver_avisos_path"               = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_avisos/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/aemet_prevision_avisos/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aemet_prevision_avisos]
}

resource "aws_glue_job" "aemet_prevision_avisos_silver_to_gold" {
  name        = "${local.glue_aemet_prevision_avisos_prefix}-silver-to-gold"
  description = "Silver -> Gold de la prevision y avisos de AEMET: prevision por municipio/horizonte y avisos por zona/dia/nivel (tarea 058)."

  role_arn          = aws_iam_role.glue_aemet_prevision_avisos.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_aemet_prevision_avisos_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_prevision_path"            = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_prevision/"
    "--silver_avisos_path"               = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/aemet_avisos/"
    "--gold_prevision_path"              = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_prevision_por_municipio_leadtime/"
    "--gold_avisos_path"                 = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/aemet_avisos_por_zona_fecha_nivel/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_aemet_prevision_avisos]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (Glue, tarea 041/046/047/048/049/050/053/054/055/
# 056/057/058 extendido a un DECIMOTERCER dataset (`cams_calidad_aire`,
# previsión de calidad del aire de Copernicus CAMS para Madrid, ver doc/019,
# doc/045, `ingesta/capturas/cams_calidad_aire_madrid.py` y
# `procesamiento/silver_gold/cams_calidad_aire/`). Alcance de ESTA tarea:
# igual que el resto del patrón, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para
# una tarea posterior con revisión de plan de por medio.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/cams_calidad_aire/*`, `silver/cams_calidad_aire/*`,
# `gold/cams_calidad_aire_por_contaminante_fecha_validez/*`) -- no se
# comparte ningún rol con el resto de datasets del patrón, mismo principio
# de mínimo privilegio por dataset que ya aplicaba `ingesta` (ver
# `procesamiento/README.md`).
# ---------------------------------------------------------------------------

locals {
  glue_cams_calidad_aire_prefix = "${var.project_name}-${var.environment}-cams-calidad-aire"
}

resource "aws_s3_object" "glue_script_cams_calidad_aire_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cams_calidad_aire_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_cams_calidad_aire_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cams_calidad_aire_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_cams_calidad_aire_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_cams_calidad_aire" {
  name = "${local.glue_cams_calidad_aire_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de la previsión de calidad del aire CAMS (tarea 059)."
  assume_role_policy = data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_cams_calidad_aire_service_role" {
  role       = aws_iam_role.glue_cams_calidad_aire.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_cams_calidad_aire_data_access" {
  statement {
    sid    = "ReadBronzeCamsCalidadAire"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/cams_calidad_aire/*"]
  }

  statement {
    sid    = "ReadWriteSilverCamsCalidadAire"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en el statement de Silver de `ruido`
    # (tarea 061): marcador `_$folder$` para cuando el DataFrame de Silver
    # sale vacío.
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/cams_calidad_aire/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/cams_calidad_aire_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051,
  # incluido desde el principio en este dataset (igual que 053-058).
  statement {
    sid    = "WriteSilverQualityReportsCamsCalidadAire"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/cams_calidad_aire/*"]
  }

  statement {
    sid    = "WriteGoldCamsCalidadAirePorContaminanteFechaValidez"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/cams_calidad_aire_por_contaminante_fecha_validez/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/cams_calidad_aire_por_contaminante_fecha_validez_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForCamsCalidadAirePrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "cams_calidad_aire/*",
        "cams_calidad_aire_por_contaminante_fecha_validez/*",
        "_quality_reports/cams_calidad_aire/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets
  # -- no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogCamsCalidadAireTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_cams_calidad_aire_data_access" {
  name = "${local.glue_cams_calidad_aire_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de la previsión de calidad del aire CAMS a los buckets del lakehouse y al catalogo de Glue (tarea 059)."
  policy      = data.aws_iam_policy_document.glue_cams_calidad_aire_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_cams_calidad_aire_data_access" {
  role       = aws_iam_role.glue_cams_calidad_aire.name
  policy_arn = aws_iam_policy.glue_cams_calidad_aire_data_access.arn
}

resource "aws_glue_catalog_table" "cams_calidad_aire_silver" {
  name          = "cams_calidad_aire"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Previsión horaria de calidad del aire de Copernicus CAMS para Madrid, limpia/validada (tarea 059)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "pollutant"
      type = "string"
    }
    columns {
      name = "pollutant_code"
      type = "string"
    }
    columns {
      name = "value"
      type = "double"
    }
    columns {
      name = "unit"
      type = "string"
    }
    columns {
      name = "valid_datetime"
      type = "string"
    }
    columns {
      name = "forecast_issued_at"
      type = "string"
    }
    columns {
      name = "leadtime_hour"
      type = "int"
    }
    columns {
      name = "model"
      type = "string"
    }
    columns {
      name = "latitude"
      type = "double"
    }
    columns {
      name = "longitude"
      type = "double"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "cams_calidad_aire_gold" {
  name          = "cams_calidad_aire_por_contaminante_fecha_validez"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Previsión de calidad del aire CAMS agregada por contaminante y día que predicen (valor medio/máximo, tarea 059)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                = "parquet"
    "parquet.compression"         = "SNAPPY"
    "projection.enabled"          = "true"
    "projection.pollutant.type"   = "enum"
    "projection.pollutant.values" = "NO2,NO,SO2,O3,PM2.5,PM10,polvo"
    "storage.location.template"   = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cams_calidad_aire_por_contaminante_fecha_validez/pollutant=$${pollutant}/"
  }

  partition_keys {
    name = "pollutant"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cams_calidad_aire_por_contaminante_fecha_validez/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "pollutant_code"
      type = "string"
    }
    columns {
      name = "unit"
      type = "string"
    }
    columns {
      name = "fecha_validez"
      type = "string"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "avg_value"
      type = "double"
    }
    columns {
      name = "max_value"
      type = "double"
    }
    columns {
      name = "leadtime_hours"
      type = "array<int>"
    }
    columns {
      name = "first_forecast_issued_at"
      type = "string"
    }
    columns {
      name = "last_forecast_issued_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_cams_calidad_aire" {
  name              = "/aws-glue/jobs/${local.glue_cams_calidad_aire_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "cams_calidad_aire_bronze_to_silver" {
  name        = "${local.glue_cams_calidad_aire_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de la previsión de calidad del aire CAMS: normalización, puerta de calidad por contaminante (tarea 059)."

  role_arn          = aws_iam_role.glue_cams_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cams_calidad_aire_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/cams_calidad_aire/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/cams_calidad_aire/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cams_calidad_aire]
}

resource "aws_glue_job" "cams_calidad_aire_silver_to_gold" {
  name        = "${local.glue_cams_calidad_aire_prefix}-silver-to-gold"
  description = "Silver -> Gold de la previsión de calidad del aire CAMS: valor medio/máximo por contaminante y día que predicen (tarea 059)."

  role_arn          = aws_iam_role.glue_cams_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cams_calidad_aire_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cams_calidad_aire_por_contaminante_fecha_validez/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cams_calidad_aire]
}

# Jobs de un solo uso (tarea 077) para reconstruir Silver/Gold de
# cams_calidad_aire deduplicados desde cero -- ver
# procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup*.py.
resource "aws_s3_object" "glue_script_cams_calidad_aire_backfill_dedup" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cams_calidad_aire_backfill_dedup-${filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup.py")
}

resource "aws_glue_job" "cams_calidad_aire_silver_backfill_dedup" {
  name        = "${local.glue_cams_calidad_aire_prefix}-silver-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion deduplicada de Silver de cams_calidad_aire desde cero, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_cams_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--bronze_path"                      = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/cams_calidad_aire/"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/"
    "--quality_report_path"              = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/cams_calidad_aire/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cams_calidad_aire]
}

resource "aws_s3_object" "glue_script_cams_calidad_aire_backfill_dedup_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/cams_calidad_aire_backfill_dedup_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/cams_calidad_aire/glue_backfill_dedup_gold.py")
}

resource "aws_glue_job" "cams_calidad_aire_gold_backfill_dedup" {
  name        = "${local.glue_cams_calidad_aire_prefix}-gold-backfill-dedup"
  description = "USO UNICO (tarea 077): reconstruccion completa de Gold de cams_calidad_aire desde el Silver ya deduplicado, no forma parte del pipeline incremental de produccion."

  role_arn          = aws_iam_role.glue_cams_calidad_aire.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 90
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cams_calidad_aire/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cams_calidad_aire_por_contaminante_fecha_validez/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cams_calidad_aire]
}

# ---------------------------------------------------------------------------
# Bronze -> Silver -> Gold (Glue, tarea 041/046/047/048/049/050/053/054/055/
# 056/057/058/059 extendido a un DECIMOCUARTO dataset (`afluencia_lugares`,
# afluencia estimada de lugares conocidos de Madrid vía la librería
# `populartimes`, ver doc/012 y
# `procesamiento/silver_gold/afluencia_lugares/`). Alcance de ESTA tarea:
# igual que el resto del patrón, solo código/infraestructura, sin
# `terraform apply` -- `terraform plan`/`apply` de este bloque quedan para
# una tarea posterior con revisión de plan de por medio.
#
# Este dataset sigue bloqueado en producción (sin `GOOGLE_MAPS_API_KEY`
# real, ver doc/012): la infraestructura se deja lista igualmente, mismo
# criterio que la propia tarea 012 dejó el código de ingesta listo sin poder
# ejecutar una captura real.
#
# Reutiliza el mismo artefacto de librería (`data.archive_file.procesamiento_source`
# ya empaqueta TODO `procesamiento/`, incluido este subpaquete nuevo, sin
# ningún cambio en esa definición) pero con su PROPIO rol IAM acotado por
# prefijo (`bronze/afluencia_lugares_patron_tipico/*` -- el nombre de
# dataset Bronze real que escribe `DATASET_NAME` en
# `ingesta/capturas/afluencia_lugares_madrid.py`, no `afluencia_lugares` --,
# `silver/afluencia_lugares/*`, `gold/afluencia_lugares_por_lugar_fecha_hora/*`)
# -- no se comparte ningún rol con el resto de datasets del patrón, mismo
# principio de mínimo privilegio por dataset que ya aplicaba `ingesta` (ver
# `procesamiento/README.md`).
#
# NOTA (tarea 061): esta sección se aplicó contra AWS real por primera vez
# en un intento previo de la tarea 061 que no llegó a commitear sus
# cambios (ver doc/061); ese intento ya había corregido el prefijo Bronze
# de esta nota (`afluencia_lugares` -> `afluencia_lugares_patron_tipico`)
# directamente en AWS, así que el código aquí se restaura para que
# coincida con lo ya aplicado.
# ---------------------------------------------------------------------------

locals {
  glue_afluencia_lugares_prefix = "${var.project_name}-${var.environment}-afluencia-lugares"
}

resource "aws_s3_object" "glue_script_afluencia_lugares_bronze_to_silver" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/afluencia_lugares_bronze_to_silver-${filemd5("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_bronze_to_silver.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_bronze_to_silver.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_bronze_to_silver.py")
}

resource "aws_s3_object" "glue_script_afluencia_lugares_silver_to_gold" {
  bucket  = aws_s3_bucket.build_artifacts.id
  key     = "glue-scripts/afluencia_lugares_silver_to_gold-${filemd5("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_silver_to_gold.py")}.py"
  content = file("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_silver_to_gold.py")

  etag = filemd5("${path.module}/../../procesamiento/silver_gold/afluencia_lugares/glue_silver_to_gold.py")
}

data "aws_iam_policy_document" "glue_afluencia_lugares_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_afluencia_lugares" {
  name = "${local.glue_afluencia_lugares_prefix}-glue-role"

  description        = "Rol asumido por los jobs de Glue de Bronze->Silver->Gold de afluencia de lugares (tarea 060)."
  assume_role_policy = data.aws_iam_policy_document.glue_afluencia_lugares_assume_role.json
}

resource "aws_iam_role_policy_attachment" "glue_afluencia_lugares_service_role" {
  role       = aws_iam_role.glue_afluencia_lugares.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_afluencia_lugares_data_access" {
  statement {
    sid    = "ReadBronzeAfluenciaLugares"
    effect = "Allow"

    actions = ["s3:GetObject"]
    # El nombre de dataset Bronze real que escribe
    # `ingesta/capturas/afluencia_lugares_madrid.py` (`DATASET_NAME`) es
    # `afluencia_lugares_patron_tipico`, no `afluencia_lugares` -- este
    # statement quedó con el prefijo equivocado desde la tarea 060 (un
    # intento previo de la tarea 061 ya lo había corregido y aplicado
    # contra AWS real sin llegar a commitear el cambio; se restaura aquí
    # para que el código commiteado coincida con la infraestructura ya
    # aplicada).
    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/afluencia_lugares_patron_tipico/*"]
  }

  statement {
    sid    = "ReadWriteSilverAfluenciaLugares"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Hueco de permisos detectado por el job de sanidad de la tarea 061:
    # falta el marcador `_$folder$` que crea el committer de Spark cuando
    # el DataFrame de Silver sale vacío (mismo problema que ya se corrigió
    # a nivel Gold en la tarea 051, ver comentario del statement de Gold
    # de este mismo fichero).
    resources = [
      "${aws_s3_bucket.lakehouse["silver"].arn}/afluencia_lugares/*",
      "${aws_s3_bucket.lakehouse["silver"].arn}/afluencia_lugares_$folder$",
    ]
  }

  # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052):
  # hueco de permisos detectado por el job de sanidad de la tarea 051,
  # incluido desde el principio en este dataset (igual que 053-059).
  statement {
    sid    = "WriteSilverQualityReportsAfluenciaLugares"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/_quality_reports/afluencia_lugares/*"]
  }

  statement {
    sid    = "WriteGoldAfluenciaLugaresPorLugarFechaHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    # Ver comentario equivalente en `glue_trafico_data_access` (tarea 052).
    resources = [
      "${aws_s3_bucket.lakehouse["gold"].arn}/afluencia_lugares_por_lugar_fecha_hora/*",
      "${aws_s3_bucket.lakehouse["gold"].arn}/afluencia_lugares_por_lugar_fecha_hora_$folder$",
    ]
  }

  statement {
    sid    = "ListLakehouseBucketsForAfluenciaLugaresPrefixes"
    effect = "Allow"

    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.lakehouse["bronze"].arn,
      aws_s3_bucket.lakehouse["silver"].arn,
      aws_s3_bucket.lakehouse["gold"].arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "afluencia_lugares_patron_tipico/*",
        "afluencia_lugares/*",
        "afluencia_lugares_por_lugar_fecha_hora/*",
        "_quality_reports/afluencia_lugares/*",
        "glue-temp/*",
      ]
    }
  }

  statement {
    sid    = "ReadOwnScriptAndLibrary"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/glue-scripts/*", "${aws_s3_bucket.build_artifacts.arn}/glue-libs/*"]
  }

  # Directorio `--TempDir`, mismo criterio que el resto de datasets del
  # patrón: bucket Silver, prefijo `glue-temp/` (compartido entre datasets
  # -- no es dato persistente, solo shuffle spill/ficheros temporales de
  # escritura).
  statement {
    sid    = "GlueTempDir"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/glue-temp/*"]
  }

  statement {
    sid    = "GlueCatalogAfluenciaLugaresTables"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:BatchCreatePartition",
      "glue:CreatePartition",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
      aws_glue_catalog_database.silver.arn,
      aws_glue_catalog_database.gold.arn,
      "${aws_glue_catalog_database.silver.arn}/*",
      "${aws_glue_catalog_database.gold.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_afluencia_lugares_data_access" {
  name = "${local.glue_afluencia_lugares_prefix}-data-access"

  description = "Acceso minimo (lectura/escritura acotada por prefijo) de Bronze->Silver->Gold de afluencia de lugares a los buckets del lakehouse y al catalogo de Glue (tarea 060)."
  policy      = data.aws_iam_policy_document.glue_afluencia_lugares_data_access.json
}

resource "aws_iam_role_policy_attachment" "glue_afluencia_lugares_data_access" {
  role       = aws_iam_role.glue_afluencia_lugares.name
  policy_arn = aws_iam_policy.glue_afluencia_lugares_data_access.arn
}

resource "aws_glue_catalog_table" "afluencia_lugares_silver" {
  name          = "afluencia_lugares"
  database_name = aws_glue_catalog_database.silver.name
  description   = "Afluencia estimada (en vivo y patrón típico) de lugares conocidos de Madrid, limpia/validada (tarea 060)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                   = "parquet"
    "parquet.compression"            = "SNAPPY"
    "projection.enabled"             = "true"
    "projection.fecha.type"          = "date"
    "projection.fecha.range"         = "2026-08-01,NOW+1DAY"
    "projection.fecha.format"        = "yyyy-MM-dd"
    "projection.fecha.interval"      = "1"
    "projection.fecha.interval.unit" = "DAYS"
    "projection.hora.type"           = "integer"
    "projection.hora.range"          = "0,23"
    "projection.hora.digits"         = "2"
    "storage.location.template"      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/afluencia_lugares/fecha=$${fecha}/hora=$${hora}/"
  }

  partition_keys {
    name = "fecha"
    type = "string"
  }

  partition_keys {
    name = "hora"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/afluencia_lugares/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "place_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "query"
      type = "string"
    }
    columns {
      name = "address"
      type = "string"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "live_pct"
      type = "int"
    }
    columns {
      name = "typical_by_hour"
      type = "struct<lunes:array<int>,martes:array<int>,miercoles:array<int>,jueves:array<int>,viernes:array<int>,sabado:array<int>,domingo:array<int>>"
    }
    columns {
      name = "ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "afluencia_lugares_gold" {
  name          = "afluencia_lugares_por_lugar_fecha_hora"
  database_name = aws_glue_catalog_database.gold.name
  description   = "Afluencia de lugares de Madrid agregada por lugar, fecha y hora: afluencia en vivo media y valor típico correspondiente (tarea 060)."

  table_type = "EXTERNAL_TABLE"

  parameters = {
    classification                  = "parquet"
    "parquet.compression"           = "SNAPPY"
    "projection.enabled"            = "true"
    "projection.date.type"          = "date"
    "projection.date.range"         = "2026-08-01,NOW+1DAY"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/afluencia_lugares_por_lugar_fecha_hora/date=$${date}/"
  }

  partition_keys {
    name = "date"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/afluencia_lugares_por_lugar_fecha_hora/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "schema_version"
      type = "int"
    }
    columns {
      name = "place_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "hour"
      type = "int"
    }
    columns {
      name = "day_of_week"
      type = "string"
    }
    columns {
      name = "samples_count"
      type = "bigint"
    }
    columns {
      name = "avg_live_pct"
      type = "double"
    }
    columns {
      name = "typical_pct"
      type = "double"
    }
    columns {
      name = "lat"
      type = "double"
    }
    columns {
      name = "lon"
      type = "double"
    }
    columns {
      name = "first_ingested_at"
      type = "string"
    }
    columns {
      name = "last_ingested_at"
      type = "string"
    }
    columns {
      name = "processed_at"
      type = "string"
    }
  }
}

resource "aws_cloudwatch_log_group" "glue_afluencia_lugares" {
  name              = "/aws-glue/jobs/${local.glue_afluencia_lugares_prefix}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_glue_job" "afluencia_lugares_bronze_to_silver" {
  name        = "${local.glue_afluencia_lugares_prefix}-bronze-to-silver"
  description = "Bronze -> Silver de afluencia de lugares: normalización, puerta de calidad de live_pct/typical_by_hour (tarea 060)."

  role_arn          = aws_iam_role.glue_afluencia_lugares.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_afluencia_lugares_bronze_to_silver.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--additional-python-modules"        = var.great_expectations_pip_spec
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    # Ver comentario en `ReadBronzeAfluenciaLugares` de este mismo fichero:
    # el dataset Bronze real es `afluencia_lugares_patron_tipico`.
    "--bronze_path"         = "s3://${aws_s3_bucket.lakehouse["bronze"].bucket}/afluencia_lugares_patron_tipico/"
    "--silver_path"         = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/afluencia_lugares/"
    "--quality_report_path" = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/_quality_reports/afluencia_lugares/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_afluencia_lugares]
}

resource "aws_glue_job" "afluencia_lugares_silver_to_gold" {
  name        = "${local.glue_afluencia_lugares_prefix}-silver-to-gold"
  description = "Silver -> Gold de afluencia de lugares: afluencia en vivo media y valor típico por lugar/fecha/hora (tarea 060)."

  role_arn          = aws_iam_role.glue_afluencia_lugares.arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.glue_script_afluencia_lugares_silver_to_gold.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.build_artifacts.bucket}/${aws_s3_object.procesamiento_source.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/afluencia_lugares/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/afluencia_lugares_por_lugar_fecha_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_afluencia_lugares]
}

# ---------------------------------------------------------------------------
# Grupos de log globales de AWS Glue (`--enable-continuous-cloudwatch-log`,
# activo en todos los jobs de este fichero): AWS Glue los crea
# automáticamente la primera vez que cualquier job escribe en ellos -- no
# son un recurso por dataset como `aws_cloudwatch_log_group.glue_<dataset>`
# de más arriba, son compartidos por TODOS los jobs de la cuenta/región.
# Se gestionan aquí solo para fijar su retención (coste mínimo, mismo
# criterio que `var.lambda_log_retention_days` en el resto del proyecto):
# sin retención explícita, CloudWatch los conserva indefinidamente. Se
# detectó real en producción (revisión de factura, no en una tarea)
# 1.78 GB acumulados sin expirar en `/aws-glue/jobs/error` +
# `/aws-glue/jobs/logs-v2` -- fijado a 14 días vía `aws logs
# put-retention-policy` antes de escribir este bloque; importar con
# `terraform import 'aws_cloudwatch_log_group.glue_shared["error"]'
# /aws-glue/jobs/error` (y el equivalente para `logs-v2`/`output`) para que
# quede bajo control de Terraform, o simplemente confirmar con `terraform
# plan` que no genera diff (ya tienen la retención fijada a mano).
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "glue_shared" {
  for_each = toset(["error", "logs-v2", "output"])

  name              = "/aws-glue/jobs/${each.key}"
  retention_in_days = var.lambda_log_retention_days
}
