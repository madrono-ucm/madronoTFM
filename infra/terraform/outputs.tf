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
  description = "ARN (con versión) de la Lambda Layer de dependencias de terceros publicada por la tarea 032 y conectada a las 14 funciones de productores por la tarea 033 (var.lambda_dependencies_layer_arn en terraform.tfvars)."
  value       = aws_lambda_layer_version.ingesta_dependencies.arn
}

output "glue_trafico_bronze_to_silver_job_name" {
  description = "Nombre del job de Glue Bronze->Silver de tráfico (tarea 041, piloto sin aplicar). Dispara una ejecución con `aws glue start-job-run --job-name <este-valor>`."
  value       = aws_glue_job.trafico_bronze_to_silver.name
}

output "glue_trafico_silver_to_gold_job_name" {
  description = "Nombre del job de Glue Silver->Gold de tráfico (tarea 041, piloto sin aplicar)."
  value       = aws_glue_job.trafico_silver_to_gold.name
}

output "glue_trafico_role_arn" {
  description = "ARN del rol IAM que asumen ambos jobs de Glue del piloto de tráfico (tarea 041)."
  value       = aws_iam_role.glue_trafico.arn
}

output "glue_catalog_database_names" {
  description = "Nombre de las bases de datos del catálogo de Glue creadas para Silver/Gold (tarea 041)."
  value = {
    silver = aws_glue_catalog_database.silver.name
    gold   = aws_glue_catalog_database.gold.name
  }
}

output "kafka_instance_id" {
  description = "ID de la instancia EC2 del broker Kafka autogestionado (tarea 042, plan sin aplicar). Útil para `aws ssm start-session --target <este-valor>`."
  value       = aws_instance.kafka.id
}

output "kafka_instance_private_ip" {
  description = "IP privada de la instancia de Kafka -- el valor que debe usar cualquier productor/consumidor dentro de la VPC como `bootstrap.servers` (tarea 042)."
  value       = aws_instance.kafka.private_ip
}

output "kafka_security_group_id" {
  description = "ID del security group del broker Kafka (tarea 042): puerto de cliente acotado a la VPC, sin SSH."
  value       = aws_security_group.kafka.id
}

output "kafka_topic_names" {
  description = "Nombre de cada topic inicial de Kafka, por clave de local.kafka_topics (tarea 042)."
  value       = local.kafka_topic_names
}

output "athena_workgroup_name" {
  description = "Nombre del workgroup de Athena para consultar Silver/Gold (tarea 066). Úsalo con `aws athena start-query-execution --work-group <este-valor>`."
  value       = aws_athena_workgroup.silver_gold.name
}

output "athena_results_bucket_name" {
  description = "Nombre del bucket S3 dedicado a resultados de consulta de Athena (tarea 066)."
  value       = aws_s3_bucket.athena_results.bucket
}

output "athena_query_role_arn" {
  description = "ARN del rol IAM de mínimo privilegio para consultar Silver/Gold vía Athena (tarea 066)."
  value       = aws_iam_role.athena_query.arn
}
