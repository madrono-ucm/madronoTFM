---
id: 41
slug: kafka-autogestionado
title: "Kafka autogestionado en EC2 (ruta caliente) — infraestructura, sin aplicar"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-15T09:49:55+00:00"
updated_at: "2026-08-15T09:49:55+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

La memoria (apartado 5.2) describe una arquitectura lambda: una ruta caliente en
streaming (Kafka) además de la ruta fría por lotes (ya construida: Lambda +
EventBridge Scheduler → Bronze). Ya se decidió con el usuario, en una sesión
anterior, ir con **Kafka autogestionado en una EC2** en vez de MSK gestionado, por
coste (principio de coste mínimo, memoria 5.4). Todavía no se ha empezado.

**Alcance: solo escribir infraestructura como código, no aplicar nada en AWS.**

## Objetivo

Escribir el Terraform de una EC2 dedicada a Kafka (separada de la EC2 de este
pipeline de tareas, para no interferir con ella) con Kafka instalado y
configurado, más la definición de los topics iniciales.

## Alcance concreto

1. Investiga y decide: ¿Kafka con ZooKeeper o modo KRaft (sin ZooKeeper, más
   simple de operar, estándar desde Kafka 3.x)? Documenta la elección.
2. Terraform: una `aws_instance` nueva (tipo pequeño, coherente con el principio
   de coste mínimo — documenta el tamaño elegido y por qué), su security group
   (acceso mínimo: el puerto de Kafka accesible solo desde dentro de la VPC/otros
   recursos del proyecto, nunca abierto a `0.0.0.0/0`), y un script de
   aprovisionamiento (`user_data` o similar) que instale y arranque Kafka.
3. Define, como código (Terraform o un script de inicialización), los topics
   iniciales razonables para las fuentes ya en producción (tráfico, EMT, BiciMAD,
   aparcamientos, calidad del aire — las de mayor frecuencia, ver la tabla de
   schedules ya establecida) — nombres de topic, particiones, factor de
   replicación (con una sola EC2, replicación 1 es lo único posible; documenta esa
   limitación).
4. Documenta en un README nuevo (p.ej. `infra/kafka/README.md`) el diseño, cómo se
   conectaría un productor real (los `TODO(kafka)` ya marcados en cada módulo de
   `ingesta/capturas/`), y una estimación básica de coste.

## Restricciones

- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- No conectes todavía ningún productor real a Kafka (los `TODO(kafka)` siguen
  como están) — es infraestructura, no el cableado de los productores.
- No dupliques recursos ya existentes (VPC/subnets: reutiliza los que ya usa el
  resto de `infra/terraform/` si existen, no crees una VPC nueva salvo que haga
  falta y lo documentes).

## Criterios de aceptación

- Terraform de la EC2 de Kafka + topics iniciales, escrito y con `terraform
  validate` limpio, sin aplicar.
- README documentando diseño, coste estimado, y cómo se conectarían los
  productores en el futuro.
