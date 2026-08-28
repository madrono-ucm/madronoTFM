---
kind: vic
title: "Memoria §5 Arquitectura — reescribir a la pila real (decisión coste 0)"
owner: Víctor
status: pending
created_at: "2026-08-28"
---

## Secciones

§5.1 Diagrama general · §5.2 Descripción de la arquitectura técnica ·
§5.3 Justificación de tecnologías · §5.4 Costes · §5.5 DevOps.

## Fuente técnica (leer primero)

- `PLATFORM_SCHEMA.md` — inventario verificado contra la cuenta AWS real
  (tarea 084).
- `NEXT_STEPS.md` §"Estado a 28/8" — tabla "memoria ↔ realidad".
- `doc/001` (infra Terraform), `doc/029`/`doc/030` (Lambda + EventBridge),
  `doc/041` (piloto Silver/Gold), `doc/064`/`doc/065` (scheduling Glue),
  `doc/066`/`doc/068` (Athena + Partition Projection), `doc/043` +
  `grafo/README.md` (grafo Neo4j), `doc/044` + `asistente/README.md`
  (asistente FastAPI/MCP).
- `infra/terraform/` — `lambda.tf`, `glue.tf`, `glue_scheduling.tf`,
  `athena.tf`. `kafka.tf` existe pero **está excluido del apply** a
  propósito (tarea 042/098).

## Qué cambia respecto al borrador de junio

| Borrador dice | Escribir |
|---|---|
| Ingesta con Apache Kafka + Kafka Connect + registro Avro | **EventBridge Scheduler + AWS Lambda** (1 función + 1–N schedules por productor; ~21 schedules). Kafka → §7.5 |
| Ruta caliente Flink/KSQL, ventanas en streaming | **No se implementó ruta caliente.** El "estado instantáneo" de cada señal es la última fila de la capa Gold (agregación horaria por Glue). Decirlo explícitamente |
| Lakehouse con tablas Delta en 3 capas | **Parquet** en 3 buckets S3 (bronze/silver/gold) + **catálogo de Glue** + **Athena con Partition Projection** (sin `MSCK REPAIR`). Sin Delta Lake |
| Spark ejecuta el batch | **AWS Glue** (Spark gestionado) ejecuta Bronze→Silver→Gold; orquestado con **Glue Triggers** (scheduled + conditional), no Airflow |
| Capa MLOps: MLflow + Evidently + ONNX | Se usan, pero describir sobre el pipeline real `modelado/` (feature store → CV temporal → registry → drift → ONNX). Ver tickets de ML |
| Explotación: Power BI + asistente | Solo **asistente** (FastAPI + agente MCP). Power BI → §7.5 |

## Qué se mantiene

- El criterio de decisión de §5.3/§5.4: **coste mínimo / coste 0**. Reforzarlo
  como el motivo por el que se eligió serverless gestionado (Lambda/Glue/
  Athena, todos con free tier real) en lugar de operar Kafka/Flink/Spark.
- El grafo Neo4j como decisión de diseño central (§5.3, párrafo del grafo)
  — sigue siendo cierto y central (ahora más: es el sustrato del GNN).
- §5.5 DevOps: las puertas de calidad Great Expectations **sí existen** por
  dataset (`procesamiento/silver_gold/*/ge_suite.py`, informes en
  `silver/_quality_reports/`). El versionado de contrato por esquema Avro
  no; describir el contrato real (esquema normalizado por
  `normalize_record` en cada captura, `schema_version` en el propio dato).

## Aceptación

- §5 no contiene ninguna afirmación desmentida por `PLATFORM_SCHEMA.md`.
- El diagrama de §5.1 refleja fuentes → Lambda → S3/Glue → Athena + Neo4j →
  asistente / modelado (sin Kafka, sin Flink, sin Power BI).
- Kafka/Flink/Delta/Power BI aparecen solo en §7.5, con una frase de por qué
  se descartaron (coste 0 / alcance).
