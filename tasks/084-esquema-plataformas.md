---
id: 84
slug: esquema-plataformas
title: "Esquema de plataformas y arquitectura"
status: in_review
force: false
allow_infra_apply: false
branch: task/084-esquema-plataformas
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-25T00:00:00+00:00'
updated_at: '2026-08-25T00:00:00+00:00'
started_at: '2026-08-25T00:00:00+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Parte de la revisión de arquitectura del 25/8 (ver tarea 083). Se pidió un
esquema detallado de todas las plataformas usadas hasta ahora — no un
inventario superficial, sino uno que refleje el estado real verificado
contra la cuenta AWS y documente los riesgos activos encontrados en la
tarea 083.

## Qué se hizo

- Se creó `PLATFORM_SCHEMA.md` en la raíz: inventario de AWS (S3, Lambda,
  EventBridge Scheduler, Glue, Athena, SSM, IAM, CloudWatch, CodeBuild,
  Kafka) y de plataformas externas (data.madrid.es, EMT, AEMET, CAMS,
  Bluesky, Google Maps, Neo4j AuraDB, GitHub), con un diagrama Mermaid del
  flujo de datos.
- Cada recuento se verificó en vivo contra la cuenta real
  (`eu-west-1`, `222234418587`) al inicio de la sesión, no se copió de
  documentación histórica.
- Se añadió una sección "Riesgos activos" que traslada los hallazgos de la
  tarea 083 (drift de Terraform, alcance de IAM del deployer, footgun de
  `-target`/`-destroy`, 3 tablas Gold rotas, sin Cost Explorer) al
  documento de arquitectura.

## Criterios de aceptación

- `PLATFORM_SCHEMA.md` existe en la raíz, con inventario AWS + externo y
  diagrama Mermaid.
- Los números citados son verificables contra la cuenta real a fecha
  25/8/2026 (documentado en `doc/084-esquema-plataformas.md`).
- Google Maps aparece marcado como descartado, no como bloqueador
  pendiente, coherente con la decisión de la tarea 083.
