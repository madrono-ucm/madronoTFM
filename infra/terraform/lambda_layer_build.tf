# ---------------------------------------------------------------------------
# Tarea 032: Lambda Layer de dependencias de terceros (ingesta/requirements.txt)
# construida vía AWS CodeBuild, gestionado por AWS -- sin instalar nada ni
# construir ninguna wheel en la EC2 de disco limitado que ejecuta Terraform.
#
# Por qué CodeBuild y no `pip install --target` en esta EC2 (ver tarea 029):
# algunas dependencias tienen extensiones nativas compiladas (netCDF4) y
# necesitan una wheel binariamente compatible con el runtime real de Lambda
# (Amazon Linux 2023 x86_64, Python 3.13). CodeBuild ofrece una imagen
# gestionada por AWS pensada exactamente para esto:
# "aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13" -- mismo
# entorno que ejecuta la función Lambda en producción.
#
# Flujo (ver doc/032-lambda-layer-codebuild.md para el detalle de la
# ejecución real):
#   1. `terraform apply` crea el bucket de artefactos, sube el .zip fuente
#      (solo requirements.txt) y crea el proyecto CodeBuild + su rol IAM.
#      `aws_lambda_layer_version` NO se puede crear todavía en este primer
#      apply: `lambda:PublishLayerVersion` necesita que el .zip de la Layer
#      ya exista en S3, y ese .zip lo genera el build, no Terraform.
#   2. Se dispara el build a mano (`aws codebuild start-build
#      --project-name <nombre>`) y se espera a que termine -- el buildspec
#      (buildspec_layer.yml) hace `pip install -r requirements.txt --target
#      python/` (convención de Lambda Layers) y sube python.zip a S3.
#   3. Un segundo `terraform apply` sí puede crear `aws_lambda_layer_version`
#      (el objeto S3 ya existe) y publica la Layer.
#
# Esta tarea NO conecta la Layer a las 14 funciones de productores:
# `var.lambda_dependencies_layer_arn` sigue en `null` en terraform.tfvars
# (eso es la tarea 033).
# ---------------------------------------------------------------------------

locals {
  codebuild_project_name = "${var.project_name}-${var.environment}-lambda-dependencies-layer"

  # Incluye el hash del fichero en la key: si `ingesta/requirements.txt`
  # cambia, el .zip fuente sube a una key nueva (evita servir a CodeBuild un
  # source S3 obsoleto cacheado bajo la misma key tras un `terraform apply`
  # que no vaya seguido de un nuevo `start-build`).
  layer_source_key   = "source/ingesta-requirements-${filemd5("${path.module}/../../ingesta/requirements.txt")}.zip"
  layer_artifact_key = "layers/ingesta-dependencies/layer.zip"
}

# ---------------------------------------------------------------------------
# Bucket S3 dedicado a artefactos de build (fuente que lee CodeBuild + Layer
# .zip que produce). Deliberadamente NO es el bucket Bronze del lakehouse:
# Bronze es para datos de producción de los productores, no para artefactos
# de infraestructura/CI -- mezclar ambos complicaría las políticas IAM de
# mínimo privilegio de `aws_iam_role.ingestion` sin ningún beneficio.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "build_artifacts" {
  bucket = "${var.project_name}-${var.environment}-build-artifacts-${data.aws_caller_identity.current.account_id}"

  tags = {
    Purpose = "lambda-layer-build"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "build_artifacts" {
  bucket = aws_s3_bucket.build_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "build_artifacts" {
  bucket = aws_s3_bucket.build_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Los .zip fuente antiguos (una key nueva por cada cambio de
# requirements.txt, ver local.layer_source_key) no hace falta conservarlos
# indefinidamente: expiran solos. El artefacto de la Layer (`layers/`) NO se
# expira: es el entregable de esta tarea.
resource "aws_s3_bucket_lifecycle_configuration" "build_artifacts" {
  bucket = aws_s3_bucket.build_artifacts.id

  rule {
    id     = "expire-old-source-zips"
    status = "Enabled"

    filter {
      prefix = "source/"
    }

    expiration {
      days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "build_artifacts_bucket_policy" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [aws_s3_bucket.build_artifacts.arn, "${aws_s3_bucket.build_artifacts.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "build_artifacts" {
  bucket = aws_s3_bucket.build_artifacts.id
  policy = data.aws_iam_policy_document.build_artifacts_bucket_policy.json
}

# .zip fuente que lee CodeBuild: únicamente `ingesta/requirements.txt`,
# aplanado a "requirements.txt" en la raíz del .zip (ver buildspec_layer.yml).
# No hace falta ningún otro fichero de `ingesta/` para construir la Layer.
data "archive_file" "layer_build_source" {
  type        = "zip"
  output_path = "${path.module}/build/layer_build_source.zip"

  source {
    filename = "requirements.txt"
    content  = file("${path.module}/../../ingesta/requirements.txt")
  }
}

resource "aws_s3_object" "layer_build_source" {
  bucket = aws_s3_bucket.build_artifacts.id
  key    = local.layer_source_key
  source = data.archive_file.layer_build_source.output_path
  etag   = data.archive_file.layer_build_source.output_md5

  server_side_encryption = "AES256"
}

# ---------------------------------------------------------------------------
# Rol IAM de CodeBuild: permisos mínimos (logs propios, leer el .zip fuente,
# escribir el .zip de la Layer). Nada de acceso a Bronze/Silver/Gold ni a
# ningún otro recurso del proyecto.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_layer_codebuild_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["codebuild.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_layer_codebuild" {
  name = "${var.project_name}-${var.environment}-lambda-layer-codebuild-role"

  description        = "Rol asumido por AWS CodeBuild para construir la Lambda Layer de dependencias de terceros de ingesta/requirements.txt (tarea 032)."
  assume_role_policy = data.aws_iam_policy_document.lambda_layer_codebuild_assume_role.json
}

data "aws_iam_policy_document" "lambda_layer_codebuild" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.codebuild_project_name}",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/codebuild/${local.codebuild_project_name}:*",
    ]
  }

  statement {
    sid    = "ReadBuildSource"
    effect = "Allow"

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/source/*"]
  }

  statement {
    sid    = "WriteLayerArtifact"
    effect = "Allow"

    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.build_artifacts.arn}/layers/*"]
  }
}

resource "aws_iam_role_policy" "lambda_layer_codebuild" {
  name   = "${var.project_name}-${var.environment}-lambda-layer-codebuild-policy"
  role   = aws_iam_role.lambda_layer_codebuild.id
  policy = data.aws_iam_policy_document.lambda_layer_codebuild.json
}

# ---------------------------------------------------------------------------
# Proyecto CodeBuild. `NO_ARTIFACTS`: el buildspec sube el .zip a S3 él
# mismo (`aws s3 cp`) en vez de delegarlo en el bloque `artifacts` de
# CodeBuild, para controlar exactamente la key de destino
# (local.layer_artifact_key) sin depender de las reglas de packaging/naming
# de artifacts de CodeBuild.
# ---------------------------------------------------------------------------

resource "aws_codebuild_project" "lambda_dependencies_layer" {
  name        = local.codebuild_project_name
  description = "Construye (pip install) las dependencias de terceros de ingesta/requirements.txt en una imagen compatible con el runtime de Lambda python3.13 x86_64, y sube el .zip resultante a S3 para publicarlo como Lambda Layer (tarea 032)."

  service_role = aws_iam_role.lambda_layer_codebuild.arn

  # Compute AWS Lambda (no EC2) para este proyecto: arranque más rápido y
  # más barato que un compute EC2 (`BUILD_GENERAL1_*`) para un build tan
  # pequeño como este. Restricción real de este modo (no de esta tarea):
  # el timeout de build es fijo en 15 minutos (el de Lambda), CodeBuild no
  # admite fijar `build_timeout`/`queued_timeout` con este compute -- de ahí
  # que no se declaren aquí. Si `netCDF4`/`cdsapi` necesitaran más de 15
  # minutos de instalación (no ha sido el caso, ver
  # doc/032-lambda-layer-codebuild.md), habría que migrar a compute EC2
  # (`BUILD_GENERAL1_SMALL` + `environment.type = "LINUX_CONTAINER"` con
  # una imagen `LINUX_CONTAINER`, no la variante `*-lambda-standard`).
  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_LAMBDA_2GB"
    image                       = "aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13"
    type                        = "LINUX_LAMBDA_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "ARTIFACT_BUCKET"
      value = aws_s3_bucket.build_artifacts.bucket
    }

    environment_variable {
      name  = "ARTIFACT_KEY"
      value = local.layer_artifact_key
    }
  }

  source {
    type      = "S3"
    location  = "${aws_s3_bucket.build_artifacts.bucket}/${local.layer_source_key}"
    buildspec = file("${path.module}/buildspec_layer.yml")
  }

  logs_config {
    cloudwatch_logs {
      status = "ENABLED"
    }
  }

  depends_on = [
    aws_s3_object.layer_build_source,
    aws_iam_role_policy.lambda_layer_codebuild,
  ]
}

# ---------------------------------------------------------------------------
# Lambda Layer. IMPORTANTE: este recurso solo se puede crear (o actualizar)
# una vez que el .zip ya existe en S3 en `local.layer_artifact_key` --
# `lambda:PublishLayerVersion` lee el objeto en el momento de publicar, y
# Terraform no dispara el build de CodeBuild por sí solo (ver cabecera del
# fichero). Tras el primer `terraform apply` (que crea todo lo anterior),
# hace falta `aws codebuild start-build --project-name
# <local.codebuild_project_name>`, esperar a que termine, y solo entonces
# un segundo `terraform apply` publica esta Layer.
# ---------------------------------------------------------------------------

resource "aws_lambda_layer_version" "ingesta_dependencies" {
  layer_name  = "${var.project_name}-${var.environment}-ingesta-dependencies"
  description = "Dependencias de terceros de ingesta/requirements.txt (requests, boto3, populartimes, cdsapi, netCDF4, beautifulsoup4), construidas vía AWS CodeBuild (tarea 032) con la imagen aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13."

  s3_bucket = aws_s3_bucket.build_artifacts.bucket
  s3_key    = local.layer_artifact_key

  compatible_runtimes      = [var.lambda_runtime]
  compatible_architectures = ["x86_64"]
}
