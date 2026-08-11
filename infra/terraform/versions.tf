terraform {
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend remoto (S3 + bloqueo por DynamoDB). Un bloque `backend` no admite
  # interpolación de variables de Terraform, así que aquí solo se declara el
  # tipo de backend; los valores concretos (bucket, key, region,
  # dynamodb_table) se pasan en tiempo de `terraform init` con
  # `-backend-config=backend.hcl` (ver `backend.hcl.example` y el README).
  #
  # El bucket de estado y la tabla de locking NO los crea este proyecto: es
  # un paso 0 manual, único, previo al primer `terraform init` (ver README).
  backend "s3" {}
}
