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

  statement {
    sid    = "WriteGoldTraficoPorPuntoHora"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.lakehouse["gold"].arn}/trafico_por_punto_hora/*"]
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/glue-temp/"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/trafico/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/trafico_por_punto_hora/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_trafico]
}
