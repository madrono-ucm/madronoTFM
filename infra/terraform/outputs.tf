output "lakehouse_bucket_names" {
  description = "Nombre de cada bucket S3 del lakehouse, por capa."
  value       = { for layer, bucket in aws_s3_bucket.lakehouse : layer => bucket.bucket }
}

output "lakehouse_bucket_arns" {
  description = "ARN de cada bucket S3 del lakehouse, por capa."
  value       = { for layer, bucket in aws_s3_bucket.lakehouse : layer => bucket.arn }
}

output "ingestion_role_arn" {
  description = "ARN del rol IAM que deben asumir los servicios de ingesta para escribir en Bronze."
  value       = aws_iam_role.ingestion.arn
}

output "ingestion_policy_arn" {
  description = "ARN de la policy IAM de escritura en Bronze adjunta al rol de ingesta."
  value       = aws_iam_policy.ingestion_bronze_write.arn
}

output "aws_account_id" {
  description = "ID de la cuenta AWS en la que se ha desplegado la infraestructura."
  value       = data.aws_caller_identity.current.account_id
}
