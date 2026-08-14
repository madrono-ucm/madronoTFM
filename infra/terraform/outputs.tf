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

output "producer_lambda_function_names" {
  description = "Nombre de cada función Lambda de productor, por clave de local.producers (tarea 029)."
  value       = { for key, fn in aws_lambda_function.producer : key => fn.function_name }
}

output "producer_lambda_function_arns" {
  description = "ARN de cada función Lambda de productor, por clave de local.producers (tarea 029)."
  value       = { for key, fn in aws_lambda_function.producer : key => fn.arn }
}

output "producer_schedule_names" {
  description = "Nombre de cada schedule de EventBridge Scheduler, por clave de local.schedules (tarea 029)."
  value       = { for key, sch in aws_scheduler_schedule.producer : key => sch.name }
}

output "scheduler_role_arn" {
  description = "ARN del rol IAM que EventBridge Scheduler asume para invocar las funciones Lambda de productores (tarea 029)."
  value       = aws_iam_role.scheduler.arn
}

output "secret_ssm_parameter_names" {
  description = "Nombre (no valor) de cada parámetro SSM SecureString placeholder que debe rellenarse a mano con la credencial real (tarea 029)."
  value       = { for key, param in aws_ssm_parameter.secrets : key => param.name }
}

output "lambda_layer_codebuild_project_name" {
  description = "Nombre del proyecto CodeBuild que construye la Lambda Layer de dependencias de terceros (tarea 032). Dispara un build con `aws codebuild start-build --project-name <este-valor>`."
  value       = aws_codebuild_project.lambda_dependencies_layer.name
}

output "lambda_dependencies_layer_arn" {
  description = "ARN (con versión) de la Lambda Layer de dependencias de terceros publicada por la tarea 032. Todavía NO conectada a las 14 funciones de productores (var.lambda_dependencies_layer_arn sigue en null en terraform.tfvars) -- eso es la tarea 033."
  value       = aws_lambda_layer_version.ingesta_dependencies.arn
}
