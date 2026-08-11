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
