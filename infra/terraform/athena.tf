# ---------------------------------------------------------------------------
# Tarea 066: capa de consulta SQL sobre Silver/Gold con Amazon Athena.
#
# Athena es el motor de consulta serverless nativo de AWS sobre el catálogo
# de Glue: sin ningún clúster que mantener (coste solo por bytes escaneados
# por consulta), consistente con el principio de coste mínimo ya aplicado a
# Lambda/Glue en el resto del proyecto. Las 30 tablas de Silver/Gold ya
# existen en el catálogo (`aws_glue_catalog_table.*`, `glue.tf`) -- este
# fichero solo añade el workgroup, el bucket de resultados y el rol IAM de
# consulta; no toca ninguna tabla ni ningún job existente.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Bucket S3 dedicado a resultados de consulta de Athena (uno nuevo, no un
# prefijo de `aws_s3_bucket.build_artifacts`).
#
# Se elige un bucket nuevo, no un prefijo del bucket de artefactos de build,
# por el mismo motivo ya documentado en `main.tf` para "un bucket por capa"
# del lakehouse: mantener la política IAM de mínimo privilegio simple y
# difícil de equivocar (el rol de consulta referencia el ARN de este bucket
# completo, sin depender de acertar un `Condition` de prefijo dentro de un
# bucket compartido con artefactos de CI/CD que no tienen nada que ver con
# resultados de consulta de datos de producción). El coste de un bucket
# vacío adicional es cero.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "athena_results" {
  bucket = "${var.project_name}-${var.environment}-athena-results-${data.aws_caller_identity.current.account_id}"

  tags = {
    Purpose = "athena-query-results"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Los resultados de consulta son completamente reproducibles (basta con
# relanzar la misma consulta): no hace falta conservarlos más que unos
# pocos días, para no acumular coste de almacenamiento indefinidamente.
resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"

    filter {}

    expiration {
      days = var.athena_results_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "athena_results_bucket_policy" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.athena_results.arn, "${aws_s3_bucket.athena_results.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  policy = data.aws_iam_policy_document.athena_results_bucket_policy.json
}

# ---------------------------------------------------------------------------
# Workgroup de Athena.
#
# `enforce_workgroup_configuration = true`: obliga a que cualquier consulta
# lanzada en este workgroup use la configuración de aquí (output_location,
# cifrado) aunque el cliente que la lance intente pasar la suya -- evita que
# un cliente mal configurado escriba resultados fuera del bucket dedicado.
#
# `bytes_scanned_cutoff_per_query`: salvaguarda de coste. 1 GiB es
# generoso frente al volumen real actual (Silver completo son ~392MB, Gold
# ~5.8MB a fecha de esta tarea -- ver doc/066-consulta-athena-silver-gold.md
# para la medición real), así que ninguna consulta legítima sobre un único
# dataset debería acercarse a este límite; sí corta en seco un `JOIN` sin
# condición o una consulta que escanee por accidente muchas más particiones
# de las esperadas.
resource "aws_athena_workgroup" "silver_gold" {
  name        = "${var.project_name}-${var.environment}-silver-gold"
  description = "Workgroup de Athena para consultar con SQL las tablas Silver/Gold del lakehouse (tarea 066)."

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_bytes_scanned_cutoff

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Rol IAM dedicado de consulta, en vez de reutilizar el rol de despliegue de
# Terraform (`madrono-terraform-deployerEC2`, que ya tiene permisos amplios
# para poder aplicar cualquier infraestructura del proyecto).
#
# Se crea un rol nuevo, de mínimo privilegio (solo lectura de Silver/Gold +
# catálogo de Glue + Athena + escritura acotada al bucket de resultados),
# porque el consumidor real de esta capa de consulta (un futuro dashboard
# BI, QuickSight, o un analista humano) no debería heredar los permisos de
# despliegue de infraestructura del rol de Terraform -- mismo criterio de
# mínimo privilegio ya aplicado al rol de ingesta (`aws_iam_role.ingestion`,
# `main.tf`) frente al rol de Terraform.
#
# Igual que `ingestion_trusted_services`/`ingestion_trusted_arns`: todavía
# no existe un consumidor concreto (no hay ningún QuickSight ni Lambda de
# BI en este proyecto a fecha de esta tarea), así que la política de
# confianza se deja parametrizada por variable en vez de fijar un único
# principal a mano -- por defecto confía en la cuenta AWS del propio
# proyecto (root), de forma que cualquier IAM user/role de la cuenta al que
# se le conceda `sts:AssumeRole` sobre este rol (por separado, en su propia
# policy) puede asumirlo para consultar, sin tener que volver a tocar este
# fichero cuando se elija un consumidor concreto.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "athena_query_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  dynamic "statement" {
    for_each = length(var.athena_query_trusted_services) > 0 ? [1] : []

    content {
      effect  = "Allow"
      actions = ["sts:AssumeRole"]

      principals {
        type        = "Service"
        identifiers = var.athena_query_trusted_services
      }
    }
  }
}

resource "aws_iam_role" "athena_query" {
  name = "${var.project_name}-${var.environment}-athena-query-role"

  description        = "Rol de mínimo privilegio para consultar Silver/Gold vía Athena (tarea 066): sin permisos de escritura sobre el lakehouse ni de despliegue de infraestructura."
  assume_role_policy = data.aws_iam_policy_document.athena_query_assume_role.json
}

data "aws_iam_policy_document" "athena_query" {
  statement {
    sid    = "AthenaQuery"
    effect = "Allow"

    actions = [
      "athena:StartQueryExecution",
      "athena:StopQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetQueryRuntimeStatistics",
      "athena:ListQueryExecutions",
      "athena:GetWorkGroup",
    ]

    resources = [aws_athena_workgroup.silver_gold.arn]
  }

  statement {
    sid    = "GlueCatalogReadOnly"
    effect = "Allow"

    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
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

  statement {
    sid    = "ReadSilverGoldData"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.lakehouse["silver"].arn,
      "${aws_s3_bucket.lakehouse["silver"].arn}/*",
      aws_s3_bucket.lakehouse["gold"].arn,
      "${aws_s3_bucket.lakehouse["gold"].arn}/*",
    ]
  }

  statement {
    sid    = "WriteQueryResults"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.athena_results.arn,
      "${aws_s3_bucket.athena_results.arn}/*",
    ]
  }
}

resource "aws_iam_policy" "athena_query" {
  name = "${var.project_name}-${var.environment}-athena-query"

  description = "Lectura de Silver/Gold + catálogo de Glue + Athena, y escritura acotada al bucket de resultados de consulta (tarea 066)."
  policy      = data.aws_iam_policy_document.athena_query.json
}

resource "aws_iam_role_policy_attachment" "athena_query" {
  role       = aws_iam_role.athena_query.name
  policy_arn = aws_iam_policy.athena_query.arn
}
