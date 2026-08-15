# ---------------------------------------------------------------------------
# Tarea 042: Kafka autogestionado en una EC2 dedicada (ruta caliente, ver
# apartado 5.2 de la memoria: además de la ruta fría por lotes ya construida
# -- Lambda + EventBridge Scheduler -> Bronze --, un broker Kafka para
# streaming). Ya se decidió con el usuario, en una sesión anterior, ir con
# Kafka autogestionado en EC2 en vez de MSK gestionado, por coste (principio
# de coste mínimo, apartado 5.4). Ver infra/kafka/README.md para el diseño
# completo, estimación de coste y cómo se conectarían los productores.
#
# **Alcance de esta tarea: solo código, sin `terraform apply`** -- mismo
# patrón que las tareas 001/041. Esta EC2 es independiente de la que ejecuta
# este pipeline de tareas (esa no se gestiona con este Terraform en
# absoluto) y de las funciones Lambda de productores (lambda.tf, tarea 029):
# ninguna Lambda se conecta a este broker todavía, los `TODO(kafka)` de
# `ingesta/capturas/` quedan sin tocar.
#
# KRaft (sin ZooKeeper) en vez de modo ZooKeeper clásico: es el modo nativo
# de gestión de metadatos de Kafka desde la serie 3.x, sin un segundo
# servicio (ZooKeeper) que desplegar/parchear/monitorizar por separado --
# menos piezas móviles en una única EC2 que ya es, de por sí, la limitación
# de HA de este diseño (ver más abajo). ZooKeeper además ya se declaró
# formalmente deprecado a partir de Kafka 3.5 y eliminado en Kafka 4.0: no
# tendría sentido construir sobre un modo en retirada.
# ---------------------------------------------------------------------------

locals {
  kafka_name_prefix = "${var.project_name}-${var.environment}-kafka"

  # Topics iniciales: uno por cada uno de los 5 productores de mayor
  # frecuencia ya en producción (ver `local.schedules` en lambda.tf: los
  # tres a 5 minutos -- trafico/emt/bicimad -- más aparcamientos
  # (15 min) y calidad_aire (cada 20 min, cron 15,35,55)). El resto de
  # productores (meteorología horaria, ruido/afluencia/aforos diarios o más
  # espaciados, fuentes de referencia sin periodicidad...) no encajan con el
  # caso de uso de una "ruta caliente" de streaming y se quedan, por ahora,
  # solo con la ruta fría por lotes ya existente -- ampliar esta lista es
  # tan sencillo como añadir una entrada aquí.
  #
  # `retention_hours`: cuánto se conserva un mensaje en el topic antes de
  # purgarse (no es el almacenamiento a largo plazo -- ese sigue siendo
  # Bronze en S3 vía la ruta fría). 24h para las fuentes a 5 minutos (el
  # caso de uso es consumo casi en tiempo real; una ventana de un día de
  # margen ya cubre cualquier reproceso/backfill razonable de un consumidor
  # caído). 72h para aparcamientos/calidad_aire, algo más de margen porque
  # su cadencia más baja hace que "un día de historial" sea una ventana de
  # menos mensajes de repuesto si un consumidor tarda en recuperarse.
  kafka_topics = {
    trafico = {
      partitions      = 3
      retention_hours = 24
    }
    transporte_publico_emt = {
      partitions      = 3
      retention_hours = 24
    }
    bicimad = {
      partitions      = 3
      retention_hours = 24
    }
    aparcamientos = {
      partitions      = 3
      retention_hours = 72
    }
    calidad_aire = {
      partitions      = 3
      retention_hours = 72
    }
  }

  # Mismo nombre que usan el bucket Bronze (prefijo del dataset) y la
  # función Lambda del productor correspondiente (`local.producers` en
  # lambda.tf) -- facilita mapear topic <-> dataset <-> productor a simple
  # vista cuando se conecte el primer productor real.
  kafka_topic_names = {
    for key, cfg in local.kafka_topics :
    key => "${var.project_name}-${var.environment}-${key}"
  }

  # Una línea "topic:particiones:retention_ms" por topic, consumida por el
  # script de aprovisionamiento (templates/kafka_bootstrap.sh.tpl) para
  # crear los topics con `kafka-topics.sh --create --if-not-exists`. La
  # definición vive aquí (Terraform), no repetida a mano en el script, para
  # que `local.kafka_topics` sea la única fuente de verdad.
  kafka_topics_spec = join("\n", [
    for key, cfg in local.kafka_topics :
    "${local.kafka_topic_names[key]}:${cfg.partitions}:${cfg.retention_hours * 3600000}"
  ])

  # CIDR con permiso de entrada al puerto de cliente de Kafka: por defecto
  # (sin `var.kafka_allowed_cidr_blocks`), el CIDR completo de la VPC por
  # defecto -- "solo desde dentro de la VPC", nunca 0.0.0.0/0 (ver la
  # validación de la variable). Nunca vacío en `aws_security_group.kafka`:
  # con el default de la variable, aquí siempre queda al menos un CIDR.
  kafka_allowed_cidr_blocks = length(var.kafka_allowed_cidr_blocks) > 0 ? var.kafka_allowed_cidr_blocks : [data.aws_vpc.default.cidr_block]
}

# ---------------------------------------------------------------------------
# Red: se reutiliza la VPC/subredes por defecto de la cuenta/región. Este
# proyecto no ha creado (ni crea aquí) una VPC propia -- las 14 funciones
# Lambda de productores (lambda.tf) no tienen `vpc_config`, corren fuera de
# cualquier VPC. Crear una VPC nueva solo para esta única EC2 añadiría NAT
# Gateway/Elastic IP (o, sin NAT, VPC endpoints de SSM) como coste
# recurrente sin ningún beneficio real todavía: la VPC por defecto ya
# ofrece una subred pública con salida a Internet (para instalar Kafka y
# para que el agente SSM llegue a sus endpoints públicos) y el mismo
# aislamiento de capa 3 vía security group para acotar el puerto de Kafka a
# "solo dentro de la VPC". Si en el futuro los productores (Lambdas) se
# adjuntan a una VPC para hablar con este broker por IP privada, ese es el
# momento de evaluar subredes privadas + NAT propias -- no antes (ver
# infra/kafka/README.md, "Cómo se conectaría un productor real").
# ---------------------------------------------------------------------------

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# AMI pública gestionada por AWS, siempre la Amazon Linux 2023 x86_64 más
# reciente en la región -- evita fijar (y tener que actualizar a mano) un ID
# de AMI concreto. Ver `lifecycle.ignore_changes` en `aws_instance.kafka`
# más abajo: sin eso, cada AMI nueva que publique AWS forzaría un reemplazo
# de la instancia en el siguiente `plan`/`apply`.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---------------------------------------------------------------------------
# Security group: acceso mínimo.
#   - Ingreso del puerto de cliente Kafka SOLO desde `local.kafka_allowed_cidr_blocks`
#     (CIDR de la VPC por defecto; nunca 0.0.0.0/0, forzado también por la
#     validación de `var.kafka_allowed_cidr_blocks`). Ningún productor puede
#     alcanzarlo hoy (las Lambdas no están en la VPC), pero deja el puerto
#     ya acotado correctamente para cuando se conecten, sin tener que tocar
#     el security group entonces.
#   - Ningún puerto de controller (KRaft) abierto: en este despliegue de un
#     solo nodo, `controller.quorum.voters=1@localhost:<puerto>` en
#     server.properties hace que ese tráfico sea siempre loopback, nunca
#     necesita alcanzarse desde fuera de la instancia.
#   - Nada de puerto 22/SSH abierto: la gestión de la instancia es vía AWS
#     Systems Manager Session Manager (rol IAM más abajo), que no necesita
#     ningún puerto de entrada -- el agente SSM abre la conexión hacia
#     fuera.
#   - Egreso abierto (`dnf install`, descarga del .tgz de Kafka desde
#     archive.apache.org, endpoints públicos de SSM). Podría acotarse más
#     con VPC endpoints/una lista de dominios permitidos, pero eso añade
#     coste recurrente o complejidad que no se justifica para un piloto de
#     un único nodo sin tráfico de entrada expuesto.
# ---------------------------------------------------------------------------

resource "aws_security_group" "kafka" {
  name        = "${local.kafka_name_prefix}-sg"
  description = "Kafka de ${local.kafka_name_prefix}: puerto de cliente solo desde la VPC, sin SSH (gestion via SSM). Tarea 042."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Puerto de cliente Kafka (PLAINTEXT), solo desde dentro de la VPC."
    from_port   = var.kafka_broker_port
    to_port     = var.kafka_broker_port
    protocol    = "tcp"
    cidr_blocks = local.kafka_allowed_cidr_blocks
  }

  egress {
    description = "Salida abierta: instalacion de paquetes/descarga del binario de Kafka y endpoints publicos del agente SSM."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.kafka_name_prefix}-sg"
  }
}

# ---------------------------------------------------------------------------
# Rol IAM de la instancia: únicamente lo necesario para SSM Session Manager
# (gestión sin SSH, sin key pair que custodiar). No se le da ningún permiso
# sobre S3/Bronze ni sobre ningún otro recurso del proyecto -- esta tarea no
# conecta el broker a nada todavía, y cuando se conecte algún productor real
# lo hará él mismo con su propio rol IAM (el productor escribe al topic, no
# el broker el que lee/escribe en S3).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "kafka_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "kafka" {
  name = "${local.kafka_name_prefix}-role"

  description        = "Rol de la instancia EC2 de Kafka: únicamente SSM Session Manager para gestión sin SSH (tarea 042)."
  assume_role_policy = data.aws_iam_policy_document.kafka_assume_role.json
}

resource "aws_iam_role_policy_attachment" "kafka_ssm" {
  role       = aws_iam_role.kafka.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "kafka" {
  name = "${local.kafka_name_prefix}-profile"
  role = aws_iam_role.kafka.name
}

# ---------------------------------------------------------------------------
# La instancia EC2. Ver variables.tf (kafka_instance_type, kafka_root_volume_gb,
# kafka_version...) para el detalle de cada elección de tamaño/versión.
# ---------------------------------------------------------------------------

resource "aws_instance" "kafka" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.kafka_instance_type
  subnet_id              = sort(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.kafka.id]
  iam_instance_profile   = aws_iam_instance_profile.kafka.name

  # IP pública solo para tráfico de SALIDA (instalación de paquetes,
  # endpoints de SSM): el security group no abre ningún puerto de entrada
  # salvo el de Kafka, acotado a la VPC -- tener IP pública no expone el
  # broker a Internet.
  associate_public_ip_address = true

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.kafka_root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/templates/kafka_bootstrap.sh.tpl", {
    kafka_version   = var.kafka_version
    scala_version   = var.kafka_scala_version
    broker_port     = var.kafka_broker_port
    controller_port = var.kafka_controller_port
    heap_mb         = var.kafka_heap_mb
    topics_spec     = local.kafka_topics_spec
  })

  tags = {
    Name = local.kafka_name_prefix
  }

  lifecycle {
    # El parámetro SSM de la AMI apunta siempre a la última AL2023
    # publicada: sin ignorar este atributo, cada AMI nueva de AWS forzaría
    # un reemplazo (y pérdida de los datos en el volumen raíz, que no es
    # persistente entre instancias) en el siguiente `plan`/`apply`, incluso
    # sin ningún cambio real de este proyecto. Actualizar el SO es una
    # operación deliberada y separada (p.ej. sustituir la instancia a
    # mano en una ventana de mantenimiento), no un efecto colateral de
    # tocar cualquier otra cosa de este fichero.
    ignore_changes = [ami]
  }
}
