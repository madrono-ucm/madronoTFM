# 042 — Kafka autogestionado en EC2 (ruta caliente), solo infraestructura

## Qué se implementó

Terraform de la ruta caliente en streaming (memoria, apartado 5.2): un broker
Kafka autogestionado en una única EC2, ya decidido con el usuario en una
sesión anterior frente a MSK gestionado por coste (principio de coste
mínimo, apartado 5.4). **Alcance de esta tarea: solo código, sin `terraform
apply`** — mismo patrón que las tareas 001/041. Ningún productor real se ha
conectado: los `TODO(kafka)` de `ingesta/capturas/` quedan sin tocar.

Ficheros nuevos:

- `infra/terraform/kafka.tf`: security group, rol IAM (solo SSM, sin SSH), la
  instancia EC2 y los topics iniciales (como `local.kafka_topics`).
- `infra/terraform/templates/kafka_bootstrap.sh.tpl`: script de
  aprovisionamiento (`user_data`) que instala Kafka en modo KRaft y crea los
  topics en el primer arranque.
- `infra/kafka/README.md`: diseño completo, estimación de coste y guía de
  conexión de productores futuros.

Ficheros modificados:

- `infra/terraform/variables.tf`: nuevas variables (`kafka_instance_type`,
  `kafka_root_volume_gb`, `kafka_version`, `kafka_scala_version`,
  `kafka_broker_port`, `kafka_controller_port`, `kafka_heap_mb`,
  `kafka_allowed_cidr_blocks` con `validation` que rechaza `0.0.0.0/0`/`::/0`).
- `infra/terraform/outputs.tf`: ID/IP privada de la instancia, ID del
  security group, nombres de los topics.
- `infra/terraform/README.md`: tabla de ficheros y la nota sobre "sin
  MSK/Kafka" (ya desactualizada tras esta tarea) actualizadas.

## Decisiones clave (por qué)

- **KRaft, no ZooKeeper**: modo nativo de Kafka desde la serie 3.x, sin un
  segundo servicio que operar; ZooKeeper está deprecado desde Kafka 3.5 y
  eliminado en 4.0. Con un solo nodo, KRaft en modo combinado
  (`process.roles=broker,controller`) es la configuración más simple: el
  propio nodo es a la vez el único broker y el único miembro del quórum de
  controladores.
- **`t3.small` (2GB RAM), heap acotado a 768MB**: piloto sin productores
  conectados todavía, 5 topics de bajo volumen — coste mínimo con margen de
  sobra. Documentado en `variables.tf` y en el README de diseño cómo subirlo
  si el throughput real lo exige.
- **Se reutiliza la VPC/subred por defecto de la cuenta**, no se crea una
  VPC propia: este proyecto no tenía ninguna hasta ahora (las 14 Lambdas de
  productores corren sin `vpc_config`), y crear una VPC dedicada solo para
  esta EC2 añadiría NAT Gateway/VPC endpoints como coste recurrente nuevo
  sin beneficio real todavía.
- **Security group de acceso mínimo**: el puerto de cliente de Kafka (9092)
  solo se abre al CIDR de la VPC por defecto, nunca a `0.0.0.0/0` — forzado
  también con una `validation` en la variable correspondiente, no solo
  documentado. Sin puerto de controller (9093) expuesto (tráfico siempre
  `localhost` en un nodo único) y **sin SSH**: la gestión de la instancia es
  vía AWS Systems Manager Session Manager (rol IAM con
  `AmazonSSMManagedInstanceCore`), sin key pair ni puertos de entrada
  adicionales.
- **5 topics iniciales** (`trafico`, `transporte_publico_emt`, `bicimad`,
  `aparcamientos`, `calidad_aire`), los productores de mayor frecuencia ya en
  producción (cadencias de 5-20 minutos, ver `local.schedules` en
  `lambda.tf`). Nombrados igual que su función Lambda/prefijo de dataset en
  Bronze, para mapear topic↔productor a simple vista. Definidos como código
  (`local.kafka_topics` en `kafka.tf`, única fuente de verdad, consumida por
  el script de aprovisionamiento) con 3 particiones cada uno y retención de
  24h (fuentes a 5 min) o 72h (aparcamientos/calidad_aire).
- **Factor de replicación 1** en los 5 topics y en los topics internos de
  Kafka (offsets, transacciones): la única opción posible con un solo
  broker. Documentado explícitamente como limitación real de durabilidad/HA
  (no un descuido), aceptable para un piloto porque Bronze en S3 sigue
  siendo el almacenamiento de registro duradero — Kafka aquí solo
  alimentaría consumidores de streaming de corto plazo.
- **AMI resuelta dinámicamente** vía el parámetro público de SSM de Amazon
  Linux 2023 más reciente, con `lifecycle.ignore_changes = [ami]` para que
  una AMI nueva publicada por AWS no fuerce un reemplazo accidental de la
  instancia (y la pérdida del volumen raíz) en un `plan`/`apply` posterior.

## Verificación

`terraform validate` limpio (provider `aws` v5.100.0, sin backend real, sin
credenciales AWS). Se detectó y corrigió en el camino un error real de
`terraform validate`: los campos `description` de `ingress`/`egress` en
`aws_security_group` solo admiten un juego de caracteres ASCII restringido
(sin tildes/acentos) — las descripciones se reescribieron sin caracteres
acentuados. `terraform fmt` limpio. No se ha ejecutado `terraform plan` ni
`apply` (sin credenciales AWS reales en esta sesión, y fuera de alcance de
todos modos).

## Cómo se conectaría un productor real (no implementado aquí)

Documentado en detalle en `infra/kafka/README.md`. Resumen: cada módulo de
`ingesta/capturas/` ya aísla su normalización (`normalize_record`) de la
escritura en Bronze, así que producir a Kafka sería un cambio local a
`capture_once`. El paso no trivial es que **las 14 funciones Lambda de
productores tendrían que adjuntarse a la VPC por defecto** (`vpc_config`,
hoy ausente en `lambda.tf`) para alcanzar el broker por IP privada — el
security group de Kafka ya está preparado para aceptar ese tráfico, pero las
Lambdas en sí no están en ninguna VPC todavía. Ese cambio tiene
implicaciones de coste/latencia (ENI por invocación concurrente) a evaluar
en la tarea que lo aborde, no en esta.

## Restricciones respetadas

- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha conectado ningún productor real: los `TODO(kafka)` de
  `ingesta/capturas/` no se han tocado.
- No se ha creado ninguna VPC nueva ni duplicado ningún recurso existente:
  se reutiliza la VPC/subred por defecto de la cuenta/región.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2
  de desarrollo — el `systemd` service de Kafka definido en
  `kafka_bootstrap.sh.tpl` es código de infraestructura para la EC2 de Kafka
  (sin aplicar), no algo ejecutado en esta sesión.

## Relevante para tareas futuras

- Conectar el primer productor real es la tarea natural siguiente: requiere
  decidir el cliente Kafka (`confluent-kafka`, con extensión nativa
  `librdkafka` y la misma fricción de empaquetado que `netCDF4` en la tarea
  032, vs. `kafka-python`, Python puro) y adjuntar las Lambdas a la VPC por
  defecto (`vpc_config` en `lambda.tf`, con su coste/latencia de ENI a
  evaluar).
- El factor de replicación 1 (limitación de un solo nodo) es la primera
  cosa a revisar si Kafka pasa de ser un piloto a una pieza crítica: la vía
  sería un clúster de 3+ nodos o migrar a MSK, ambos cambios de
  infraestructura significativos, no un ajuste de esta EC2.
- `infra/terraform/README.md` seguía documentando (antes de esta tarea) que
  "Kafka/MSK" estaba fuera de alcance sin fecha — ya se ha actualizado para
  reflejar que la ruta caliente existe como código (sin aplicar) desde esta
  tarea.
