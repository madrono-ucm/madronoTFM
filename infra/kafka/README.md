# Kafka autogestionado en EC2 (ruta caliente) — tarea 042

La memoria del TFM (apartado 5.2) describe una arquitectura lambda: además de
la ruta fría por lotes ya construida (Lambda + EventBridge Scheduler →
Bronze, tareas 026-040), una ruta caliente en streaming vía Kafka. Ya se
decidió con el usuario, en una sesión anterior, ir con **Kafka autogestionado
en una EC2** en vez de MSK (Kafka gestionado de AWS), por coste (principio de
coste mínimo, apartado 5.4). Esta tarea escribe esa infraestructura como
código Terraform (`infra/terraform/kafka.tf` + `infra/terraform/templates/kafka_bootstrap.sh.tpl`).

**Alcance de esta tarea: solo código, sin `terraform apply`.** `terraform
validate` está limpio (ver el propio `kafka.tf`); aplicarlo es una decisión y
un paso manual posterior, con revisión de plan de por medio — mismo patrón
que las tareas 001/041. No se ha conectado ningún productor real: los
`TODO(kafka)` ya marcados en cada módulo de `ingesta/capturas/` siguen tal
cual, sin tocar.

## KRaft, no ZooKeeper

Se elige **KRaft** (Kafka con gestión de metadatos propia, sin ZooKeeper) en
vez del modo ZooKeeper clásico:

- Es el modo nativo de Kafka desde la serie 3.x: una pieza menos que
  desplegar, parchear y monitorizar por separado (un segundo servicio,
  ZooKeeper, con su propio ciclo de vida) en una infraestructura que ya de
  por sí es un único nodo — más piezas móviles no compran ninguna robustez
  adicional aquí.
- ZooKeeper se declaró formalmente deprecado a partir de Kafka 3.5 y se
  eliminó por completo en Kafka 4.0: construir hoy sobre un modo en vías de
  retirada no tendría sentido.
- Para un broker de un solo nodo, KRaft en modo combinado (`process.roles=broker,controller`,
  `node.id=1`, `controller.quorum.voters=1@localhost:9093`) es la
  configuración más simple posible: el propio nodo es a la vez el único
  broker y el único miembro del quórum de controladores, sin necesidad de
  exponer el puerto de controller fuera de `localhost`.

## Tamaño de la instancia

`kafka_instance_type = "t3.small"` (2 vCPU ráfaga, 2GB RAM) por defecto —
ver el porqué completo en el comentario de la variable
(`infra/terraform/variables.tf`). Resumen: es un piloto de un único broker
en modo combinado, con 5 topics de bajo volumen de mensajes y **ningún
productor conectado todavía** (los `TODO(kafka)` siguen pendientes). El heap
de la JVM se acota explícitamente a 768MB (`kafka_heap_mb`, con margen para
el sistema operativo y la page cache de Kafka, que se beneficia de RAM
libre para servir lecturas recientes sin ir a disco). Si el throughput
real crece tras conectar productores, subir el tipo de instancia es un
cambio de una variable — documentado también ahí que eso implica sustituir
la instancia (los datos del volumen raíz no sobreviven a un cambio de
`instance_type` salvo que se gestione manualmente con `stop`/`start` en vez
de recrear el recurso).

Volumen raíz: `gp3`, 20GB por defecto (`kafka_root_volume_gb`), cifrado en
reposo. Con la retención acotada de los topics (24-72h, ver abajo) y el
volumen de mensajes de este piloto, 20GB deja margen de sobra sin
sobredimensionar.

## Red: se reutiliza la VPC por defecto, no se crea una nueva

Este proyecto no había creado hasta ahora ninguna VPC propia (`main.tf`/
`lambda.tf`): las 14 funciones Lambda de productores corren sin
`vpc_config`, fuera de cualquier VPC. Crear una VPC dedicada solo para esta
única EC2 exigiría además NAT Gateway/Elastic IP (o, sin NAT, varios VPC
endpoints de SSM) como coste recurrente nuevo, sin ningún beneficio real
todavía. Por eso `kafka.tf` reutiliza la **VPC y subred por defecto** de la
cuenta/región (`data "aws_vpc" "default"` + `data "aws_subnets" "default"`,
filtrando por `default-for-az`), que ya ofrece:

- Una subred pública con salida a Internet (necesaria para instalar Kafka —
  el binario se descarga de `archive.apache.org` — y para que el agente SSM
  llegue a sus endpoints públicos).
- El mismo aislamiento de capa 3 vía security group que necesita este
  diseño: el puerto de cliente de Kafka se acota al CIDR de esa VPC, no a
  Internet.

Si en el futuro los productores (las Lambdas) se adjuntan a una VPC propia
para hablar con este broker por IP privada de forma más aislada, ese es el
momento de evaluar subredes privadas + NAT — no antes (ver "Cómo se
conectaría un productor real" más abajo).

## Security group: acceso mínimo

- **Ingreso**: solo el puerto de cliente de Kafka (`9092` por defecto,
  `kafka_broker_port`), y solo desde el CIDR de la VPC por defecto —
  **nunca `0.0.0.0/0`**. Esto está forzado también en código: la variable
  `kafka_allowed_cidr_blocks` tiene una `validation` en `variables.tf` que
  rechaza explícitamente `0.0.0.0/0`/`::/0` si alguien la sobrescribe.
- **Nada de puerto de controller (9093) abierto**: en este despliegue de
  nodo único, el tráfico de controller de KRaft es siempre `localhost`
  (`controller.quorum.voters=1@localhost:9093`), así que no necesita
  alcanzarse desde fuera de la instancia.
- **Nada de SSH (puerto 22)**: la gestión de la instancia es vía **AWS
  Systems Manager Session Manager** (`aws ssm start-session --target
  <instance-id>`), con el rol IAM de la instancia limitado a la política
  gestionada `AmazonSSMManagedInstanceCore` — sin necesidad de un key pair
  que custodiar ni de abrir ningún puerto de entrada (el agente SSM abre la
  conexión hacia fuera, no al revés).
- **Egreso abierto** (`0.0.0.0/0`, todos los puertos): necesario para
  `dnf install`, descargar el binario de Kafka y que el agente SSM llegue a
  sus endpoints públicos. Podría acotarse más con VPC endpoints o una lista
  de dominios permitidos, pero eso añade coste recurrente o complejidad que
  no se justifica para un piloto de un único nodo sin ningún puerto de
  entrada expuesto a Internet.

La instancia tiene IP pública (`associate_public_ip_address = true`), pero
**solo para tráfico de salida** (instalación de paquetes, endpoints de SSM):
el security group no abre ningún puerto de entrada salvo el de Kafka,
acotado a la VPC, así que tener IP pública no expone el broker.

## Topics iniciales

Uno por cada uno de los 5 productores de mayor frecuencia ya en producción
(ver `local.schedules` en `infra/terraform/lambda.tf`):

| Topic (nombre real) | Dataset / productor | Cadencia actual (ruta fría) | Particiones | Retención |
|---|---|---|---|---|
| `madrono-tfm-dev-trafico` | `trafico` | cada 5 min | 3 | 24h |
| `madrono-tfm-dev-transporte_publico_emt` | `transporte_publico_emt` | cada 5 min | 3 | 24h |
| `madrono-tfm-dev-bicimad` | `bicimad` | cada 5 min | 3 | 24h |
| `madrono-tfm-dev-aparcamientos` | `aparcamientos` | cada 15 min | 3 | 72h |
| `madrono-tfm-dev-calidad_aire` | `calidad_aire` | cada 20 min (cron 15,35,55) | 3 | 72h |

El nombre de cada topic coincide con el nombre de la función Lambda del
productor correspondiente (`madrono-tfm-<entorno>-<dataset>`) y con el
prefijo de su dataset en Bronze — a propósito, para que sea trivial mapear
topic ↔ productor ↔ dataset cuando se conecte el primero.

Definidos como código en `local.kafka_topics`
(`infra/terraform/kafka.tf`), única fuente de verdad: el script de
aprovisionamiento (`templates/kafka_bootstrap.sh.tpl`) recibe la lista ya
renderizada por Terraform y crea cada topic con
`kafka-topics.sh --create --if-not-exists` en el primer arranque.

**Factor de replicación: 1 en los 5 topics, y también en los topics
internos de Kafka** (`offsets.topic.replication.factor`,
`transaction.state.log.replication.factor`, `min.insync.replicas`, todos a
`1` en `server.properties`). Es la única opción posible con un solo broker
— no hay ningún otro nodo al que replicar. Esto es una **limitación real de
disponibilidad y durabilidad**, no un descuido: si esta EC2 falla o se
pierde su volumen EBS, se pierden los mensajes aún no consumidos/persistidos
en Bronze por la ruta fría. Dado que la ruta fría (Bronze en S3, con
versionado y replicación implícita de S3) sigue siendo el almacenamiento de
registro duradero, y que Kafka aquí solo alimenta consumidores de streaming
de "casi tiempo real" con una ventana de retención corta (24-72h), este
riesgo se considera aceptable para un piloto — no lo sería para un sistema
donde Kafka fuera la única copia de los datos. Si en el futuro se necesita
tolerancia a fallos real, la vía es un clúster de 3+ nodos (con
`replication-factor=3`, `min.insync.replicas=2`) o migrar a MSK — ambas
opciones son un cambio de infraestructura significativo, no un ajuste de
esta EC2.

¿Por qué solo estos 5 topics y no los 21 productores? Los productores
restantes (meteorología horaria; ruido/afluencia/aforos diarios, semanales o
mensuales; fuentes de referencia casi estáticas como callejero/barrios/POI)
no encajan con el caso de uso de una "ruta caliente" de streaming — su
cadencia ya es tan baja que la ruta fría por lotes cubre razonablemente bien
la necesidad de frescura de datos. Ampliar esta lista más adelante es tan
sencillo como añadir una entrada a `local.kafka_topics`.

## Cómo se conectaría un productor real (fuera de alcance de esta tarea)

Cada módulo de `ingesta/capturas/` que ya tiene un `TODO(kafka)` (ver
`ingesta/README.md`) documenta el mismo patrón: la función de normalización
(`normalize_record`/`parse_records`) queda ya aislada de la escritura en
Bronze (`BronzeWriter.write_batch`), así que producir a un topic Kafka sería
un cambio local a `capture_once`, sin tocar el esquema. Cuando se aborde esa
tarea:

1. Añadir `confluent-kafka` (o `kafka-python`) a `ingesta/requirements.txt` —
   y, si los productores siguen siendo Lambda, reempaquetar la Lambda Layer
   (mismo mecanismo que las tareas 032/033) o usar `confluent-kafka`, que
   requiere una extensión nativa compilada (`librdkafka`), lo que puede
   exigir el mismo tipo de build con CodeBuild/Docker que ya resolvió
   `netCDF4` en la tarea 032 — a diferencia de `kafka-python`, que es Python
   puro y no tiene esa fricción de empaquetado (posible criterio de
   elección para esa tarea futura).
2. **Las funciones Lambda de productores tendrían que adjuntarse a la VPC
   por defecto** (`vpc_config` en `aws_lambda_function`, hoy ausente en
   `lambda.tf`) para poder alcanzar el broker por su IP privada
   (`kafka_instance_private_ip`, ver `outputs.tf`) — el security group de
   Kafka ya está preparado para aceptar ese tráfico (acotado al CIDR de la
   VPC), pero las Lambdas en sí no están en la VPC todavía. Adjuntar una
   Lambda a una VPC añade además la necesidad de una interfaz de red
   elástica (ENI) por invocación concurrente — un cambio con implicaciones
   de coste/latencia a evaluar en esa tarea, no aquí.
3. `bootstrap.servers` = `<kafka_instance_private_ip>:9092` (variable de
   entorno nueva, mismo patrón que el resto de configuración de
   `ingesta/capturas/`, no un secreto — la IP privada no es sensible dentro
   de la VPC).
4. Producir cada registro ya normalizado (el mismo `dict`/`dataclass` que
   hoy se pasa a `BronzeWriter.write_batch`) al topic correspondiente de la
   tabla de arriba, serializado igual que ya se serializa para Bronze (JSON).
   `BronzeWriter.write_batch` seguiría llamándose igual: la ruta caliente
   sería un **complemento**, no un reemplazo, de la ruta fría (memoria,
   apartado 5.2 — arquitectura lambda: ambas rutas coexisten).

Ninguno de estos 4 pasos se ha implementado en esta tarea.

## Gestión de la instancia

- **Acceso**: `aws ssm start-session --target <kafka_instance_id>` (salida de
  `outputs.tf`). Sin SSH, sin key pair.
- **Logs de aprovisionamiento**: `/var/log/kafka-bootstrap.log` en la
  instancia (todo el `user_data` redirige su salida ahí).
- **Logs del broker**: gestionados por systemd
  (`journalctl -u kafka -f` dentro de la instancia); no se ha configurado
  envío a CloudWatch Logs en esta tarea (a diferencia de las Lambdas/Glue,
  que sí tienen su log group — se deja como posible mejora futura si hace
  falta observabilidad centralizada del broker).
- **user_data solo se ejecuta una vez** (primer arranque, cloud-init): si se
  cambia el script de aprovisionamiento después de que la instancia ya
  exista, hace falta sustituir la instancia (o reaplicar el script a mano
  vía SSM) para que el cambio surta efecto — limitación inherente a
  cualquier bootstrap basado en `user_data`, documentada aquí para que no
  sorprenda en una tarea futura.
- **AMI**: Amazon Linux 2023 x86_64, resuelta dinámicamente vía el parámetro
  público de SSM `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`
  (siempre la más reciente en el momento del primer `apply`).
  `lifecycle.ignore_changes = [ami]` evita que una AMI nueva publicada por
  AWS después fuerce un reemplazo accidental de la instancia (y la pérdida
  del volumen raíz) en un `plan`/`apply` posterior que no tuviera intención
  de tocar el sistema operativo.

## Estimación de coste (aproximada, región `eu-west-1`)

| Recurso | Coste aproximado |
|---|---|
| EC2 `t3.small` on-demand (~$0.0228/h × 730h) | ~$16.6/mes |
| EBS `gp3` 20GB (~$0.096-0.11/GB-mes según región) | ~$2/mes |
| **Total EC2 autogestionado** | **~$18-19/mes** |

Sin transferencia de datos significativa que añadir: el tráfico
broker↔productores sería intra-VPC (sin coste), y la única salida real es la
instalación puntual de paquetes/Kafka en el primer arranque.

Comparación con MSK (gestionado): el propio blog de AWS ("Create Amazon MSK
clusters with T3 brokers for less than $2.50/day", 2020) sitúa el **mínimo**
de un clúster MSK funcional (varios brokers `kafka.t3.small`, el tipo más
barato que ofrece MSK) en el entorno de **~$75/mes**, y un clúster MSK de
tamaño más realista para producción (2-3 brokers `kafka.m5.large`, ~$0.21/h
por broker según el propio pricing de AWS) ronda los **$300-450/mes** — sin
contar almacenamiento EBS por broker ni el cargo adicional por hora de
clúster de MSK. Frente a eso, esta EC2 autogestionada cuesta
aproximadamente **un 75-95% menos**, a cambio de renunciar a la alta
disponibilidad multi-broker y a la gestión operativa (parcheo, escalado)
que MSK resuelve por su cuenta — trade-off que se considera aceptable para
un piloto de streaming sin productores conectados todavía (ver "Limitación
de un solo nodo" arriba). Estas cifras son una estimación de referencia, no
una cotización — conviene verificarlas en la
[calculadora de precios de AWS](https://calculator.aws) con la configuración
real antes de un `terraform apply`.

## Qué no se ha hecho en esta tarea

- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales — solo código Terraform, validado con `terraform validate`
  (limpio) pero sin ningún recurso creado en la cuenta real.
- No se ha conectado ningún productor real: los `TODO(kafka)` de
  `ingesta/capturas/` no se han tocado.
- No se ha creado ninguna VPC nueva: se reutiliza la VPC por defecto de la
  cuenta/región (ver "Red" arriba).
- No se ha configurado TLS/SASL en el listener de Kafka (PLAINTEXT dentro de
  una VPC privada, sin acceso desde Internet) ni autenticación de cliente —
  aceptable mientras el único tráfico permitido sea intra-VPC y no haya
  ningún productor conectado; a revisar si en el futuro el broker deja de
  ser de un solo nodo/uso interno.
