---
id: 93
slug: asistente-eventos-cercanos
title: 'Asistente: implementar eventos_cercanos (Prioridad 4, penúltima tool pendiente)'
status: done
force: false
allow_infra_apply: false
branch: task/093-asistente-eventos-cercanos
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-26T12:50:00Z'
started_at: '2026-08-26T12:32:00Z'
submitted_at: '2026-08-26T12:50:00Z'
merged_at: null
---

## Contexto

Continuación de la tarea 091: siguiente `tool` pendiente de
`NEXT_STEPS.md`, Prioridad 4. `eventos_cercanos` cruza un lugar contra
`agenda_eventos`, pero no hay ningún nodo `:Evento` en el grafo y Gold de
`agenda_eventos` agrega por categoría/distrito/fecha (sin lat/lon por
evento) -- no sirve para "eventos cerca de un punto".

## Qué se hizo

Primer caso de una `tool` de `asistente/` que lee **Silver**, no Gold (sí
tiene lat/lon reales por evento, validados por la puerta de calidad).
`resolver_lugar_query` (nueva, solo coordenadas, sin `PROXIMO_A`) +
`_eventos_cercanos_impl` (Neo4j para el punto de referencia, Silver para
los eventos en una ventana de 30 días, filtro por distancia Haversine real,
`_haversine_m` local) + router + 11 tests nuevos.

Verificado en vivo contra AWS **y Neo4j reales** (credenciales encontradas
en SSM -- gap de la tarea 043/081 ya cerrado sin que nadie lo documentara):
`GET /eventos-cercanos?lugar=Retiro&radio_m=2000` → 7 eventos reales y
distintos.

En la propia verificación se encontraron y corrigieron 2 bugs reales: (1)
la consulta a Silver usaba `date` en vez de `fecha` como columna de
partición (Gold renombra esa columna al agregar, Silver no); (2) el mismo
evento aparecía repetido varias veces (Silver es un log persistente, no
deduplicado -- se corrigió deduplicando por `event_id`).

Detalle completo en `doc/093-asistente-eventos-cercanos.md`.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform.
- `agenda_recintos_madrid` fuera de alcance (sin pipeline Silver/Gold).
- Credenciales de Neo4j nunca escritas a disco (leídas de SSM en memoria).
