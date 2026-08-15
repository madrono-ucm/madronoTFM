#!/bin/bash
# Aprovisionamiento de un broker Kafka de nodo único en modo KRaft (sin
# ZooKeeper). Renderizado por Terraform (kafka.tf, tarea 042) y ejecutado
# como user_data en el primer arranque de la instancia (cloud-init) -- ver
# infra/kafka/README.md para el diseño completo, incluida la decisión de
# usar KRaft en vez de ZooKeeper.
#
# Idempotencia: cloud-init solo ejecuta user_data una vez (primer arranque),
# así que la idempotencia de este script importa sobre todo si alguien lo
# vuelve a lanzar a mano (p.ej. por SSM) tras un fallo a mitad de ejecución
# -- de ahí las comprobaciones "si ya existe, no lo repitas" antes de
# descargar el tarball o formatear el almacenamiento KRaft.
set -euo pipefail

exec > >(tee -a /var/log/kafka-bootstrap.log) 2>&1
echo "[kafka-bootstrap] $(date -u --iso-8601=seconds) inicio"

KAFKA_VERSION="${kafka_version}"
SCALA_VERSION="${scala_version}"
KAFKA_HOME="/opt/kafka"
KAFKA_DATA_DIR="/var/lib/kafka/data"
KAFKA_USER="kafka"

dnf install -y java-17-amazon-corretto-headless tar gzip

id -u "$KAFKA_USER" &>/dev/null || useradd --system --home-dir "$KAFKA_HOME" --shell /sbin/nologin "$KAFKA_USER"

if [ ! -d "$KAFKA_HOME/libs" ]; then
  TARBALL_NAME="kafka_$SCALA_VERSION-$KAFKA_VERSION.tgz"
  cd /tmp
  curl -fsSL -o "$TARBALL_NAME" "https://archive.apache.org/dist/kafka/$KAFKA_VERSION/$TARBALL_NAME"
  mkdir -p "$KAFKA_HOME"
  tar -xzf "$TARBALL_NAME" -C "$KAFKA_HOME" --strip-components=1
  rm -f "$TARBALL_NAME"
fi

mkdir -p "$KAFKA_DATA_DIR"

# IP privada de la instancia (metadatos IMDSv1/v2), usada como
# advertised.listeners: los futuros clientes (dentro de la VPC) deben
# conectar por IP privada, nunca por la IP pública de gestión.
TOKEN="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')"
PRIVATE_IP="$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-ipv4)"

mkdir -p "$KAFKA_HOME/config/kraft"
cat > "$KAFKA_HOME/config/kraft/server.properties" <<EOF
process.roles=broker,controller
node.id=1
controller.quorum.voters=1@localhost:${controller_port}

listeners=PLAINTEXT://0.0.0.0:${broker_port},CONTROLLER://0.0.0.0:${controller_port}
advertised.listeners=PLAINTEXT://$PRIVATE_IP:${broker_port}
controller.listener.names=CONTROLLER
inter.broker.listener.name=PLAINTEXT
listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT

log.dirs=$KAFKA_DATA_DIR

# Broker único: factor de replicación 1 en todo (no hay otro broker al que
# replicar). Ver infra/kafka/README.md, "Limitación de un solo nodo".
num.partitions=3
default.replication.factor=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
min.insync.replicas=1

# Los topics se crean explícitamente más abajo (con su partición/retención
# propia), no de forma implícita al primer mensaje publicado.
auto.create.topics.enable=false
EOF

if [ ! -f "$KAFKA_DATA_DIR/meta.properties" ]; then
  CLUSTER_ID="$("$KAFKA_HOME/bin/kafka-storage.sh" random-uuid)"
  "$KAFKA_HOME/bin/kafka-storage.sh" format -t "$CLUSTER_ID" -c "$KAFKA_HOME/config/kraft/server.properties"
fi

chown -R "$KAFKA_USER":"$KAFKA_USER" "$KAFKA_HOME" "$KAFKA_DATA_DIR"

cat > /etc/systemd/system/kafka.service <<EOF
[Unit]
Description=Kafka (KRaft, nodo unico) - madrono-tfm (tarea 042)
After=network.target

[Service]
Type=simple
User=$KAFKA_USER
Environment=KAFKA_HEAP_OPTS=-Xmx${heap_mb}m -Xms${heap_mb}m
ExecStart=$KAFKA_HOME/bin/kafka-server-start.sh $KAFKA_HOME/config/kraft/server.properties
ExecStop=$KAFKA_HOME/bin/kafka-server-stop.sh
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now kafka

echo "[kafka-bootstrap] esperando a que el broker acepte conexiones..."
for i in $(seq 1 30); do
  if "$KAFKA_HOME/bin/kafka-broker-api-versions.sh" --bootstrap-server "localhost:${broker_port}" &>/dev/null; then
    break
  fi
  sleep 5
done

echo "[kafka-bootstrap] creando topics iniciales (si no existen)..."
while IFS=':' read -r topic_name partitions retention_ms; do
  [ -z "$topic_name" ] && continue
  "$KAFKA_HOME/bin/kafka-topics.sh" --bootstrap-server "localhost:${broker_port}" \
    --create --if-not-exists \
    --topic "$topic_name" \
    --partitions "$partitions" \
    --replication-factor 1 \
    --config "retention.ms=$retention_ms"
done <<'TOPICS_EOF'
${topics_spec}
TOPICS_EOF

echo "[kafka-bootstrap] fin $(date -u --iso-8601=seconds)"
