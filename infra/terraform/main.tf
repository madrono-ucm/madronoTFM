provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = var.project_name
        Environment = var.environment
        ManagedBy   = "terraform"
      },
      var.tags,
    )
  }
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Lakehouse medallón: un bucket S3 por capa (bronze/silver/gold).
#
# Se elige "un bucket por capa" en vez de "un bucket con prefijos" porque:
#   - Las políticas IAM de mínimo privilegio quedan mucho más simples y
#     difíciles de equivocar: el rol de ingesta referencia el ARN del bucket
#     bronze completo, en vez de tener que acertar con un `Condition` de
#     prefijo dentro de un bucket compartido con silver/gold (un error ahí
#     filtraría acceso de escritura a las otras capas).
#   - Cada capa puede tener su propio ciclo de vida, cifrado o (en el
#     futuro) replicación/retención sin afectar a las demás.
#   - El coste de tener 3 buckets vacíos en vez de 1 es cero: S3 no cobra
#     por bucket, solo por almacenamiento/requests.
# ---------------------------------------------------------------------------

locals {
  bucket_names = {
    for layer in var.medallion_layers :
    layer => "${var.project_name}-${var.environment}-${layer}-${data.aws_caller_identity.current.account_id}"
  }
}

resource "aws_s3_bucket" "lakehouse" {
  for_each = local.bucket_names

  bucket = each.value

  tags = {
    Layer = each.key
  }
}

resource "aws_s3_bucket_versioning" "lakehouse" {
  for_each = aws_s3_bucket.lakehouse

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
  for_each = aws_s3_bucket.lakehouse

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "lakehouse" {
  for_each = aws_s3_bucket.lakehouse

  bucket = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Ciclo de vida pensado para minimizar coste sin perder la capacidad de
# consultar los datos con normalidad:
#   - La versión "actual" de cada objeto pasa a Standard-IA a los N días
#     (sigue siendo consultable al instante, ~45% más barato en storage).
#     Deliberadamente NO se transiciona a Glacier la versión actual: el
#     lakehouse (sobre todo Gold) se espera consultar bajo demanda
#     (Athena/BI) y Glacier introduce minutos/horas de latencia de
#     recuperación, inaceptable para eso.
#   - Las versiones "no actuales" (sobrescritas o de objetos borrados) sí
#     van a Glacier rápido y se expiran del todo pasado un tiempo: son
#     historial de versionado, no datos que se vayan a consultar.
resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
  for_each = aws_s3_bucket.lakehouse

  bucket = each.value.id

  rule {
    id     = "cost-optimization"
    status = "Enabled"

    filter {}

    transition {
      days          = var.standard_ia_transition_days
      storage_class = "STANDARD_IA"
    }

    noncurrent_version_transition {
      noncurrent_days = var.noncurrent_version_glacier_days
      storage_class   = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.lakehouse]
}

# Exige TLS en todas las peticiones a los buckets del lakehouse. Coste cero,
# buena práctica mínima de seguridad para datos que pronto tendrán consumidores
# variados (ingesta, procesado, BI).
data "aws_iam_policy_document" "bucket_policy" {
  for_each = aws_s3_bucket.lakehouse

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lakehouse" {
  for_each = aws_s3_bucket.lakehouse

  bucket = each.value.id
  policy = data.aws_iam_policy_document.bucket_policy[each.key].json
}

# ---------------------------------------------------------------------------
# Rol IAM para los futuros servicios de ingesta (productores de datos).
# Permisos mínimos: solo escritura de objetos en el bucket Bronze, nada de
# lectura, borrado, ni acceso a Silver/Gold.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ingestion_assume_role" {
  dynamic "statement" {
    for_each = length(var.ingestion_trusted_services) > 0 ? [1] : []

    content {
      effect  = "Allow"
      actions = ["sts:AssumeRole"]

      principals {
        type        = "Service"
        identifiers = var.ingestion_trusted_services
      }
    }
  }

  dynamic "statement" {
    for_each = length(var.ingestion_trusted_arns) > 0 ? [1] : []

    content {
      effect  = "Allow"
      actions = ["sts:AssumeRole"]

      principals {
        type        = "AWS"
        identifiers = var.ingestion_trusted_arns
      }
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name = "${var.project_name}-${var.environment}-ingestion-role"

  description        = "Rol asumido por los servicios de ingesta (productores de datos) para escribir en la capa Bronze del lakehouse."
  assume_role_policy = data.aws_iam_policy_document.ingestion_assume_role.json
}

data "aws_iam_policy_document" "ingestion_bronze_write" {
  statement {
    sid    = "WriteBronzeObjects"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:PutObjectTagging",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]

    resources = ["${aws_s3_bucket.lakehouse["bronze"].arn}/*"]
  }

  statement {
    sid    = "ListBronzeBucket"
    effect = "Allow"

    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lakehouse["bronze"].arn]
  }
}

resource "aws_iam_policy" "ingestion_bronze_write" {
  name = "${var.project_name}-${var.environment}-ingestion-bronze-write"

  description = "Permite escribir objetos en el bucket Bronze del lakehouse (sin lectura ni borrado, y sin acceso a Silver/Gold)."
  policy      = data.aws_iam_policy_document.ingestion_bronze_write.json
}

resource "aws_iam_role_policy_attachment" "ingestion_bronze_write" {
  role       = aws_iam_role.ingestion.name
  policy_arn = aws_iam_policy.ingestion_bronze_write.arn
}
