---
kind: vic
title: "Memoria §6.5 Orquestación · §6.6 Almacenamiento y consulta"
owner: Víctor
status: pending
created_at: "2026-08-28"
---

## Fuente técnica

- `doc/064` (diseño scheduling Silver/Gold), `doc/065` (aplicado),
  `doc/066` (consulta Athena), `doc/068` (Partition Projection).
- `infra/terraform/glue_scheduling.tf` — triggers reales (scheduled
  `bronze-to-silver` + conditional `silver-to-gold`), cadencia por dataset
  (horaria: tráfico/calidad_aire/meteo/bicimad/aparcamientos/EMT;
  diaria 06:00: ruido/agenda/bluesky/aforos/afluencia;
  AEMET/CAMS/cartelera a horas fijas).
- `infra/terraform/athena.tf` — tablas con projection.

## Qué cambia

- **§6.5** — el borrador habla de "disparadores sobre la ruta caliente que
  activan alertas". No hay ruta caliente. Reescribir: la orquestación son
  **Glue Triggers nativos** — un trigger `SCHEDULED` lanza Bronze→Silver por
  cron, y un trigger `CONDITIONAL` lanza Silver→Gold cuando el anterior
  termina `SUCCEEDED`. Cadencia por dataset según su frecuencia de
  actualización real (tabla en `doc/064`). Las "alertas por desviación
  anómala" son una futura línea (§7.5), no algo implementado.
- **§6.6** — el borrador menciona "un almacén caliente para consulta de
  baja latencia". No existe. Reescribir: dos superficies de consulta —
  **Athena** (SQL sobre el catálogo Glow/Glue con Partition Projection, sin
  `MSCK REPAIR`) para explotación analítica y para el feature store de
  `modelado/`; **Neo4j** (AuraDB Free) para las consultas relacionales del
  asistente. El asistente accede vía su agente MCP traduciendo la pregunta a
  consultas sobre grafo + Athena.

## Qué se mantiene

- La idea de Gold como única superficie de explotación.
- Partition Projection como decisión acertada (evita un catálogo que crece
  sin control) — `doc/068`.

## Aceptación

- §6.5 describe Glue Triggers reales, no un orquestador inexistente.
- §6.6 no menciona ningún "hot store"; describe Athena + Neo4j.
