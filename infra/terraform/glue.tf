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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/ruido/*"]
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/aforos_peatones_bicicletas/*"]
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    resources = ["${aws_s3_bucket.lakehouse["silver"].arn}/cartelera_cines_estrenos/*"]
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
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
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
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--silver_path"                      = "s3://${aws_s3_bucket.lakehouse["silver"].bucket}/cartelera_cines_estrenos/"
    "--gold_path"                        = "s3://${aws_s3_bucket.lakehouse["gold"].bucket}/cartelera_cines_estrenos_por_pelicula_cine_fecha/"
  }

  depends_on = [aws_cloudwatch_log_group.glue_cartelera_cines_estrenos]
}
