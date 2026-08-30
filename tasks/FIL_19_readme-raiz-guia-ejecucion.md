---
kind: fil
title: "README raíz + guía 'ejecuta el asistente' + diagrama de arquitectura real"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: [FIL_13, FIL_15]
---

## Resolución (2026-08-30)

`README.md` raíz (antes: sólo `# madronoTFM`): qué es + enlace a la memoria,
diagrama Mermaid de la arquitectura **construida** (25 productores → Bronze
→ Glue → Silver → Glue → Gold → {Athena, Neo4j} → modelado ONNX → asistente
FastAPI+MCP → cliente MCP) con lo NO construido marcado explícito
(Kafka/Flink/Delta/Power BI/STGNN-serving/auth = §7.5), estado (pipeline
congelado, datos hasta ~29/8, enlace a `infra/OPERACION.md`), guía "ejecuta
el asistente en local" (venv + `pip install` + `NEO4J_*` de SSM + `uvicorn`
/ `python -m asistente.mcp_agent.server` + bloque `mcpServers`), puntero a
`modelado/README.md` / `VIKT_08` para la evaluación ML, y tabla de layout
del repo (una línea por directorio). Enlaza `infra/OPERACION.md` en vez de
duplicarlo.

## Contexto

El repo tiene `doc/` (100+ entradas auto-generadas), `PLAN.md`,
`NEXT_STEPS.md`, `infra/OPERACION.md` y READMEs por subpaquete, pero **no
hay un README raíz que dé la foto completa** ni una guía de "cómo levanto
esto en local". Primera impresión del proyecto y criterio de reproducibilidad
del TFM.

## Objetivo

`README.md` en la raíz, conciso, con:

1. **Qué es** — un párrafo: plataforma de datos de movilidad/vida urbana de
   Madrid + modelos predictivos + asistente MCP. Enlace a la memoria.
2. **Diagrama de arquitectura real** (Mermaid): 16 productores → Bronze
   (S3) → Glue → Silver → Glue → Gold → {Athena, Neo4j} → {`modelado/`
   (LightGBM/STGNN, MLflow, ONNX), asistente FastAPI + MCP}. Marcar
   explícitamente lo NO construido (Kafka/Flink/Delta/Power BI) como "fuera
   de alcance / §7.5".
3. **Estado** — pipeline congelado (`pipeline_enabled=false`); datos hasta
   2026-08-29; cómo reanudar.
4. **Ejecutar el asistente en local** — venv, `pip install -r
   asistente/requirements.txt`, variables (`AWS_PROFILE`, Neo4j de SSM),
   `uvicorn asistente.main:app` y/o `python -m asistente.mcp_agent.server`
   (stdio) + el `mcpServers` de ejemplo para un cliente MCP.
5. **Ejecutar la evaluación de ML** — puntero a `modelado/README.md` /
   `VIKT_08`.
6. **Layout del repo** — tabla de una línea por directorio.

## Criterios de aceptación

- Alguien que clona el repo puede, siguiendo sólo el README, levantar el
  asistente en local y llamar una tool.
- El diagrama Mermaid renderiza y coincide con lo construido.
- No duplica `infra/OPERACION.md` — enlaza.

## Restricciones

- Español, consistente con el resto de la documentación del repo.
