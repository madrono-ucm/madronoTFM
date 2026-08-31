---
kind: fil
title: "Tool MCP contexto_urbano(lugar) — consulta multi-salto genuina del grafo"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_51]
milestone: "M7"
target: "2026-09-13"
---

## Motivación

Las 12 tools actuales que tocan el grafo hacen `MATCH` de **1 salto**. Una
tool que haga un **traversal real** demuestra el valor del grafo (y encaja
con el argumento de `infra/neo4j/README.md`).

## Alcance — 13.ª tool `contexto_urbano(lugar)`

`asistente/contexto_urbano.py` + tool + router + `server.py` a 13.
Devuelve, para un `:Lugar` resuelto por texto:

- **barrio y distrito por la jerarquía real** (`UBICADO_EN` → `Barrio`
  `PERTENECE_A` → `Distrito`), no por point-in-polygon al vuelo.
- **estaciones de medida a 1 salto** (`PROXIMO_A`), por tipo
  (tráfico/aire/ruido/bici), con `distancia_m`.
- **paradas de transporte alcanzables a ≤2 saltos de `CONECTADO_CON`**
  desde la parada más cercana → "a cuántas paradas conecta este sitio sin
  cambiar demasiado".
- **otros `:Lugar` a ≤2 saltos de `PROXIMO_A`** por tipo/`osm_amenity` →
  "qué hay alrededor" (parques, aparcamientos, cines…).

## Implementación

- **Artefacto vendorizado** `asistente/modelos/grafo_urbano.json` (de
  `FIL_51`, recortado a lo que la tool necesita) + traversal en Python puro
  (BFS ≤2 saltos) — autocontenido, mismo patrón que `grafo_ruta.json` /
  `ruta_saludable`.
- Si `NEO4J_*` está presente en el entorno, una variante que hace el mismo
  traversal en Cypher nativo (`MATCH path = (l)-[:PROXIMO_A*1..2]-(x)`) —
  opcional, con fallback al artefacto.
- `RespuestaAsistente` trazable; `fiabilidad` según completitud del grafo.

## Coste

Cero AWS, cero Neo4j en runtime (salvo la variante opcional). Tests mockean.

## Resolución (2026-08-31)

- `asistente/modelos/grafo_urbano.json.gz` (copia del artefacto de `FIL_51`,
  ~0,66 MB) vendorizado.
- `asistente/contexto_urbano.py` — carga el `.gz`, indexa, BFS ≤2 saltos en
  Python puro (sin `networkx`, sin Neo4j — autocontenido).
- **13.ª tool `contexto_urbano(lugar)`** → `ContextoUrbano` (contenedor con
  `output_schema`): barrio/distrito por la jerarquía real, estaciones a 1
  salto de `PROXIMO_A` por tipo, `:Lugar` a ≤2 saltos, transporte a ≤2
  saltos de `CONECTADO_CON` desde la parada más cercana. Degrada con
  `motivo` (+ ejemplos) — nunca excepción.
- Router `GET /contexto-urbano`, `server.py` a **13 tools**,
  `test_mcp_tools`/`test_mcp_transport` a 13.
- `asistente/tests/test_contexto_urbano.py` (8).
- Ejemplo: «Retiro» → Jardines de El Buen Retiro (parque), barrio Los
  Jerónimos / distrito Retiro; 6 estaciones de tráfico a ≤300 m; 21 paradas
  alcanzables a ≤2 saltos desde «Alcalá - Puerta de Alcalá» (Cibeles,
  Círculo de Bellas Artes, Felipe II…).
- La variante Cypher-nativa (`MATCH (l)-[:PROXIMO_A*1..2]-(x)` si
  `NEO4J_*` está presente) queda para `FIL_54`.
