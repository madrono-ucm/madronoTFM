---
kind: fil
title: "Test de integración end-to-end: productor -> Gold -> grafo -> respuesta del asistente"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: []
---

## Contexto

Hay ~900 tests unitarios, pero **ninguno recorre el sistema entero**. Los
jobs de Glue no se testean (Spark no disponible en CI — `aggregate.py` es el
proxy testeado). No hay una prueba que demuestre que las piezas encajan:
un registro Bronze acaba siendo una respuesta coherente del asistente.

## Objetivo

Un test (o un pequeño conjunto) que, sin AWS ni Spark reales, recorra:

`fixture Bronze -> transform.bronze_to_silver -> aggregate.aggregate_silver_to_gold
-> (cargar en un grafo de test / mock de Neo4j) -> llamar una tool del
asistente -> aserción sobre la respuesta`.

Para al menos **un** dataset horario (p. ej. `calidad_aire`) y la tool
`calidad_aire` (+ opcionalmente `calidad_aire_prevista` con un ONNX de test).

## Alcance

1. `tests/integracion/` (nuevo, en la raíz o en `asistente/tests/`):
   - Fixture Bronze pequeña y realista (reutilizar
     `procesamiento/tests/fixtures/` si sirve).
   - Encadenar `transform` + `aggregate` en Python puro → filas "Gold".
   - Un doble de Athena que sirve esas filas Gold a las tools del asistente
     (extender el `FakeAthenaClient` existente).
   - Un doble de Neo4j con un sub-grafo mínimo (estación ↔ lugar).
   - Llamar `calidad_aire(zona, momento)` y afirmar valores/clasificación
     esperados a partir de la fixture.
2. Correr en CI (job `tests`).
3. Documentar en `doc/FIL-18-...md` qué cubre y qué no (sigue sin cubrir el
   runtime Spark real ni AWS real — eso es §7.5 / manual).

## Criterios de aceptación

- El test pasa en CI y falla si se rompe cualquier eslabón de la cadena
  (verificado introduciendo un fallo deliberado y viéndolo romper).
- `doc/FIL-18-...md` con el alcance y las limitaciones del enfoque.

## Restricciones

- Sin dependencias nuevas pesadas. Nada de `testcontainers`/Spark local en
  CI (coste/tiempo) — el objetivo es la *composición*, no el runtime.
