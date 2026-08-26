---
id: 96
slug: asistente-opciones-movilidad
title: 'Asistente: implementar opciones_movilidad, última tool de la Prioridad 4'
status: done
force: false
allow_infra_apply: false
branch: task/096-asistente-opciones-movilidad
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-26T13:45:00Z'
started_at: '2026-08-26T13:10:00Z'
submitted_at: '2026-08-26T13:45:00Z'
merged_at: null
---

## Contexto

Última `tool` pendiente de las 6 originales del esqueleto de la tarea 044
(Prioridad 4 de `NEXT_STEPS.md`). A diferencia de las demás, no hay ningún
grafo de calles transitable para calcular rutas reales entre dos puntos
(`CONECTADO_CON`, tarea 071, solo conecta paradas de transporte público a
lo largo de una línea CRTM). Confirmado con el usuario antes de
implementar: simplificación deliberada y documentada (sin routing real,
`duracion_estimada_min` siempre `None`) en vez de dejarla sin implementar
o fabricar una duración inventada.

## Qué se hizo

Nueva query builder `lugares_proximos_a_paradas_emt_query` (mismo patrón
que la de BiciMAD) + `_opciones_movilidad_impl` (resuelve origen/destino
por separado, describe tráfico/BiciMAD/EMT cerca de cada extremo) +
router + 6 tests nuevos (2 archivos, con dobles de test propios que
enrutan por lugar+tipo, ya que las tools anteriores nunca necesitaron
consultar el mismo tipo de nodo dos veces con resultados distintos).

Verificado en vivo contra AWS y Neo4j reales:
`GET /opciones-movilidad?origen=Retiro&destino=Sol` → tráfico fluido en
ambos extremos, 8.0 bicis/15.1 anclajes en BiciMAD, "sin datos" en EMT
(consistente con su cobertura real muy limitada, ya documentada en
`NEXT_STEPS.md` Prioridad 7 antes de esta tarea).

Detalle completo en `doc/096-asistente-opciones-movilidad.md`.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform.
- Ningún intento de routing real por calles (fuera de alcance).
