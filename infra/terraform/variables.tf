variable "aws_region" {
  description = <<-EOT
    Región de AWS donde se despliega toda la infraestructura.
    Por defecto `eu-west-1` (Irlanda): es la región de la UE con más
    servicios y madurez, y en general los precios de S3/DynamoDB más bajos
    de la UE, lo cual pesa más que la residencia estricta en España dado que
    el proyecto no tiene (por ahora) un requisito legal de mantener los
    datos dentro de España. Si en el futuro surge ese requisito, cambia a
    `eu-south-2` (España) — el código no asume la región en ningún sitio.
  EOT
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Prefijo corto del proyecto, usado para nombrar todos los recursos (kebab-case)."
  type        = string
  default     = "madrono-tfm"
}

variable "environment" {
  description = "Entorno de despliegue (p.ej. dev, prod). Se añade al nombre de los recursos."
  type        = string
  default     = "dev"
}

variable "medallion_layers" {
  description = "Capas del lakehouse medallón, una por bucket S3 (bucket-per-layer, ver README)."
  type        = list(string)
  default     = ["bronze", "silver", "gold"]

  validation {
    condition     = length(var.medallion_layers) == length(toset(var.medallion_layers))
    error_message = "medallion_layers no debe tener nombres de capa repetidos."
  }

  validation {
    condition     = contains(var.medallion_layers, "bronze")
    error_message = "medallion_layers debe incluir \"bronze\": el rol de ingesta (main.tf) referencia ese bucket explícitamente."
  }
}

variable "standard_ia_transition_days" {
  description = "Días tras los que un objeto (versión actual) pasa de S3 Standard a Standard-IA, más barato para datos poco accedidos."
  type        = number
  default     = 30
}

variable "noncurrent_version_glacier_days" {
  description = "Días tras los que una versión no-actual (sobrescrita/borrada) pasa a Glacier Flexible Retrieval."
  type        = number
  default     = 30
}

variable "noncurrent_version_expiration_days" {
  description = "Días tras los que una versión no-actual se elimina definitivamente, para no acumular coste de versiones antiguas indefinidamente."
  type        = number
  default     = 90
}

variable "ingestion_trusted_services" {
  description = <<-EOT
    Service principals de AWS (p.ej. "lambda.amazonaws.com") a los que se
    permite asumir el rol de ingesta. Por defecto se asume que los futuros
    productores de datos serán funciones Lambda (encajan con el principio de
    coste mínimo: sin servidores que pagar en reposo). Añade aquí otros
    servicios (p.ej. "ecs-tasks.amazonaws.com") según se implementen.
  EOT
  type        = list(string)
  default     = ["lambda.amazonaws.com"]
}

variable "ingestion_trusted_arns" {
  description = <<-EOT
    ARNs de roles/usuarios IAM concretos (fuera de un servicio AWS) a los
    que se permite asumir el rol de ingesta, p.ej. un rol de una instancia
    EC2 o de un runner de CI que vaya a subir datos manualmente. Vacío por
    defecto. Al menos uno de `ingestion_trusted_services` /
    `ingestion_trusted_arns` debe quedar no vacío, o la política de
    asunción de rol resultante no tendría ningún principal permitido.
  EOT
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags adicionales a fusionar con las tags por defecto (Project/Environment/ManagedBy) en todos los recursos."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Tarea 029: Lambda + EventBridge Scheduler para los productores de ingesta.
# ---------------------------------------------------------------------------

variable "lambda_runtime" {
  description = "Runtime de Lambda para todas las funciones de productores. python3.13 es, a fecha de esta tarea, la versión de Python 3 más reciente soportada por Lambda."
  type        = string
  default     = "python3.13"
}

variable "lambda_default_timeout_seconds" {
  description = "Timeout por defecto (segundos) de cada función Lambda de productor. Se puede sobrescribir por productor en `local.producers` (ver lambda.tf) cuando una fuente concreta lo necesite (p.ej. CAMS, que descarga un NetCDF de Copernicus)."
  type        = number
  default     = 60
}

variable "lambda_default_memory_mb" {
  description = "Memoria por defecto (MB) de cada función Lambda de productor. Se puede sobrescribir por productor en `local.producers`."
  type        = number
  default     = 256
}

variable "lambda_log_retention_days" {
  description = "Días de retención de los logs de CloudWatch de cada función Lambda de productor. Acotado (no indefinido) por coste mínimo."
  type        = number
  default     = 14
}

variable "lambda_dependencies_layer_arn" {
  description = <<-EOT
    ARN (con versión) de una Lambda Layer que contenga las dependencias de
    terceros de `ingesta/requirements.txt` (requests, beautifulsoup4,
    cdsapi, netCDF4, populartimes...), construida fuera de esta tarea con
    herramientas de build compatibles con el runtime de Lambda (Docker/
    manylinux, no esta EC2 de disco limitado). Ver doc/029 para el porqué:
    no se ha construido ninguna layer real en esta tarea, así que se deja
    en `null` (ninguna función lleva layer todavía) hasta que exista ese
    ARN real, momento en el que basta con fijarlo en `terraform.tfvars` sin
    tocar ningún `.tf`.
  EOT
  type        = string
  default     = null
}

variable "ssm_secret_placeholder_value" {
  description = <<-EOT
    Valor placeholder (NO un secreto real) con el que Terraform crea cada
    parámetro SecureString de SSM la primera vez (ver `local.secrets` en
    lambda.tf). Cada parámetro tiene `lifecycle.ignore_changes = [value]`,
    así que este placeholder solo se escribe una vez, en el primer
    `terraform apply`; el valor real se fija después a mano
    (`aws ssm put-parameter --overwrite`), fuera de git y fuera del control
    de Terraform.
  EOT
  type        = string
  default     = "CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM"
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Tarea 041: piloto Bronze -> Silver -> Gold de tráfico (AWS Glue).
# ---------------------------------------------------------------------------

variable "glue_version" {
  description = "Versión de AWS Glue (motor Spark serverless) para los jobs de procesamiento. \"4.0\" es, a fecha de esta tarea, la más reciente con soporte a largo plazo (Spark 3.3, Python 3.10)."
  type        = string
  default     = "4.0"
}

variable "glue_worker_type" {
  description = "Tipo de worker de los jobs de Glue. \"G.1X\" (4 vCPU/16GB, 1 DPU) es el tamaño mínimo recomendado por AWS para jobs Spark con memory-intensive transforms; de sobra para el volumen de un único dataset piloto."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Número de workers de cada job de Glue. El mínimo permitido (2, uno de ellos actúa de driver) — coste mínimo para un piloto de un solo dataset; subir esto es la primera palanca si el volumen crece al extender el patrón a más fuentes."
  type        = number
  default     = 2
}

variable "glue_job_timeout_minutes" {
  description = "Timeout (minutos) de cada job de Glue. Corta ejecuciones colgadas sin depender del timeout por defecto (2880 min/48h) de Glue."
  type        = number
  default     = 30
}

variable "great_expectations_pip_spec" {
  description = <<-EOT
    Especificador `pip` (nombre==versión) de Great Expectations, instalado
    en tiempo de ejecución del job de Glue vía el parámetro nativo
    `--additional-python-modules` (paquetes puros de PyPI, sin necesidad de
    una imagen/capa a medida — a diferencia de la Lambda Layer de la tarea
    032, aquí no hace falta CodeBuild/Docker porque Glue ya resuelve esto
    él solo). Versión fijada explícitamente (no un rango) para que las
    ejecuciones del job sean reproducibles. Ver
    `procesamiento/silver_gold/trafico/ge_suite.py` para el porqué de esta
    versión y de que la puerta de calidad "real" viva en Python puro
    (`transform.validate_record`), no en GX.
  EOT
  type        = string
  default     = "great_expectations==0.18.19"
}
