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

    Incluye además `urllib3<2` (tarea 051): el runtime base de Glue 4.0 trae
    preinstalado un `boto3`/`botocore` cuyo `httpsession.py` importa
    `DEFAULT_CIPHERS` de `urllib3.util.ssl_`, símbolo eliminado en la serie
    2.x de `urllib3`. Sin este pin, el propio `pip install` de
    `great_expectations` arrastra `urllib3>=2` como dependencia transitiva
    (a través de `requests`) y sobrescribe la versión 1.26.x que el
    `boto3`/`botocore` ya instalado en el runtime necesita, rompiendo su
    importación (`ImportError: cannot import name 'DEFAULT_CIPHERS'`) en
    cualquier código del job que use `boto3` después de esa instalación
    (incluida la escritura del informe de calidad a S3 vía `boto3`, ver
    `glue_bronze_to_silver.py`). `--additional-python-modules` acepta una
    lista separada por comas resuelta en una única invocación de `pip`, así
    que el resolutor de dependencias instala ambos paquetes de forma
    consistente en vez de en dos pasos separados.
  EOT
  type        = string
  default     = "great_expectations==0.18.19,urllib3<2"
}

# ---------------------------------------------------------------------------
# Tarea 042: Kafka autogestionado en una EC2 dedicada (ruta caliente, ver
# apartado 5.2 de la memoria). Ver infra/kafka/README.md para el diseño
# completo -- solo código, sin `terraform apply` (mismo patrón que las
# tareas 001/041).
# ---------------------------------------------------------------------------

variable "kafka_instance_type" {
  description = <<-EOT
    Tipo de instancia EC2 del broker Kafka. "t3.small" (2 vCPU ráfaga, 2GB
    RAM) por coste mínimo: para un único broker en modo KRaft combinado
    (broker+controller) con el volumen bajo de este piloto (5 topics, pocos
    mensajes/minuto, ningún productor conectado todavía), el heap de la JVM
    se acota a `var.kafka_heap_mb` (768MB por defecto) dejando margen de
    sobra para el sistema operativo y la page cache de Kafka. Si el
    throughput crece, subir esto es un cambio de una línea (recrea la
    instancia; los datos persisten en el volumen EBS si se usa
    `stop`+`start` en vez de `destroy`+`apply`, pero no si se cambia este
    valor con la instancia ya creada -- ver README para el detalle).
  EOT
  type        = string
  default     = "t3.small"
}

variable "kafka_root_volume_gb" {
  description = "Tamaño (GB) del volumen raíz EBS (gp3) donde Kafka guarda los segmentos de log de cada topic. 20GB de sobra para la retención acotada (24-72h) de los 5 topics iniciales a este volumen de mensajes."
  type        = number
  default     = 20
}

variable "kafka_version" {
  description = "Versión de Apache Kafka a instalar (binario oficial de archive.apache.org, no un paquete de distro). 3.9.0 es, a fecha de esta tarea, una versión estable reciente con KRaft como modo por defecto (sin ZooKeeper) desde la serie 3.x."
  type        = string
  default     = "3.9.0"
}

variable "kafka_scala_version" {
  description = "Versión de Scala del binario de Kafka a descargar (parte del nombre del tarball oficial, p.ej. kafka_2.13-3.9.0.tgz). No afecta al cliente/protocolo, solo a qué build de Scala embebe el broker."
  type        = string
  default     = "2.13"
}

variable "kafka_broker_port" {
  description = "Puerto del listener PLAINTEXT de cliente del broker Kafka (donde se conectarán los futuros productores/consumidores)."
  type        = number
  default     = 9092
}

variable "kafka_controller_port" {
  description = "Puerto del listener CONTROLLER (metadatos KRaft). Solo se usa en localhost en este despliegue de nodo único (controller.quorum.voters=1@localhost:<puerto>), así que no se abre en el security group -- ver kafka.tf."
  type        = number
  default     = 9093
}

variable "kafka_heap_mb" {
  description = "Tamaño (MB) del heap de la JVM del broker (-Xmx/-Xms). 768MB por defecto, acotado para dejar margen de RAM al sistema operativo/page cache en una instancia kafka_instance_type=\"t3.small\" (2GB); revisar al alza si se cambia a un tipo de instancia mayor."
  type        = number
  default     = 768
}

variable "kafka_allowed_cidr_blocks" {
  description = <<-EOT
    Bloques CIDR con permiso de entrada al puerto de cliente de Kafka
    (`kafka_broker_port`). Vacío por defecto: en ese caso el security group
    (kafka.tf) usa automáticamente el CIDR de la VPC por defecto de la
    cuenta/región, es decir "solo desde dentro de la VPC". Rellena esto
    explícitamente solo si hace falta acotar aún más (p.ej. a la subred
    concreta de un futuro productor). Nunca debe incluir "0.0.0.0/0" ni
    "::/0" -- la validación de abajo lo impide.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.kafka_allowed_cidr_blocks, "0.0.0.0/0") && !contains(var.kafka_allowed_cidr_blocks, "::/0")
    error_message = "kafka_allowed_cidr_blocks no debe abrir el puerto de Kafka a Internet (0.0.0.0/0 / ::/0): debe quedar acotado a la VPC u otros CIDR internos del proyecto."
  }
}
