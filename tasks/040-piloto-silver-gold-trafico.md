---
id: 40
slug: piloto-silver-gold-trafico
title: "Piloto Bronze→Silver→Gold: tráfico (Glue + Great Expectations)"
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

Hasta ahora todo el trabajo ha sido Fase 1 (Ingesta): datos reales llegando a
Bronze. La memoria (apartados 5.5, 6.2-6.4) describe el siguiente paso: limpieza y
normalización Bronze→Silver (reproyección de coordenadas, escalas 0-100%,
homogeneización de timestamps, puertas de calidad Great Expectations) y
agregación Silver→Gold, con Apache Spark como motor de procesamiento batch.
Coherente con el principio de coste mínimo ya aplicado en todo el proyecto, el
candidato natural es **AWS Glue** (Spark serverless, pago solo por uso) en vez de
un clúster Spark persistente.

Esta tarea es un **piloto**: un único dataset (tráfico — el más maduro, ya
verificado en producción, y con transformaciones bien documentadas pendientes:
reproyección EPSG:25830→WGS84, normalización de intensidad/ocupación) para
establecer el patrón, antes de extenderlo al resto de fuentes en tareas futuras.

**Alcance: solo escribir código e infraestructura, no aplicar nada en AWS** — igual
que hizo la tarea 001 con el lakehouse. Aplicar (con revisión de plan de por
medio, mismo patrón que 014/015) es una tarea posterior.

## Objetivo

Escribir el job de Glue (script PySpark) que transforma tráfico de Bronze a
Silver (limpieza, reproyección, puertas de calidad Great Expectations) y de
Silver a Gold (agregación por punto/hora, o por zona si ya se puede cruzar con
`barrios_distritos_madrid` de la tarea 010), más el Terraform que lo despliega —
sin aplicarlo.

## Alcance concreto

1. Investiga y decide: ¿Great Expectations corre dentro del propio job de Glue
   (como dependencia Python empaquetada) o como un paso separado? Documenta la
   decisión y por qué.
2. Crea un directorio nuevo para el código de transformación (p.ej.
   `procesamiento/silver_gold/trafico.py` o similar — decide una estructura
   razonable, coherente con `ingesta/` como precedente, y documenta).
3. Transformación Bronze→Silver de tráfico: reproyecta `location.x/y` (EPSG:25830)
   a lat/lon (WGS84), normaliza intensidad/ocupación/carga a escalas consistentes,
   homogeneiza `measured_at`/`ingested_at` (ya en hora de Madrid tras las tareas
   034-038), aplica puertas de calidad Great Expectations razonables (rangos
   plausibles, no nulos en campos clave) — los registros que no las pasen no
   deben llegar a Silver.
4. Transformación Silver→Gold: una agregación simple y razonable (p.ej. intensidad
   media por punto de medida y hora, o por distrito si decides cruzar con
   barrios/distritos — usa tu criterio, no hace falta el grafo completo en Neo4j
   todavía, eso es la tarea 042).
5. Terraform (`infra/terraform/`, fichero nuevo): `aws_glue_job` (o los dos, uno
   por transformación) + rol IAM de Glue con permisos mínimos (leer Bronze,
   escribir Silver/Gold, catálogo de Glue) + `aws_glue_catalog_database`/`table`
   si decides usar el catálogo.
6. Tests para la lógica de transformación que no dependan de un clúster Spark real
   (usa datos de ejemplo pequeños, verifica con `pandas`/estructuras en memoria si
   evitas levantar una sesión Spark real en los tests, o `pyspark` local si lo
   prefieres — decide y documenta el porqué).
7. Documenta en un README nuevo (p.ej. `procesamiento/README.md`) el diseño, las
   puertas de calidad aplicadas, y el criterio de agregación de Gold.

## Restricciones

- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales — solo
  código, tal como marca el system prompt para tareas sin `allow_infra_apply`.
- NO proceses datos reales de Bronze en esta tarea (no hay Glue desplegado
  todavía) — prueba la lógica de transformación con datos de ejemplo locales.
- No intentes cubrir las demás fuentes — es un piloto de un solo dataset.

## Criterios de aceptación

- Código de transformación Bronze→Silver→Gold para tráfico, con puertas de
  calidad, probado con datos de ejemplo.
- Terraform del job de Glue + permisos, escrito y con `terraform validate` limpio,
  sin aplicar.
- Documentación del diseño y las decisiones tomadas.
