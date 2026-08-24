---
id: 81
slug: asistente-tool-trafico-cercano-grafo
title: 'Asistente: tool con cruce vía grafo (trafico_cercano, Neo4j + Athena)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/081-asistente-tool-trafico-cercano-grafo
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-25T09:00:00+00:00'
updated_at: '2026-08-24T21:58:48.887192+00:00'
started_at: '2026-08-24T21:58:48.887164+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 079 implementó `calidad_aire`, la primera `tool` real del
asistente, contra Athena. La tarea 080 cargó y verificó el grafo urbano
completo en la instancia real de Neo4j AuraDB Free (9327 nodos, 41031
relaciones — ver `doc/080-cargar-grafo-neo4j-real.md`). Esta tarea es la
primera que **cruza datasets vía el grafo**, en vez de consultar una única
tabla Gold — el ejemplo que ya usa la memoria del TFM (apartado 6.7) y que
está anotado como siguiente paso en `PLAN.md`.

**Tool nueva: `trafico_cercano(lugar, radio_m=300.0, momento=None)`** — no
es una de las 5 `tools` ya declaradas en `asistente/mcp_agent/tools.py`
(esas mapean 1:1 a un origen de `ingesta/`); esta combina dos fuentes por
proximidad geográfica real, usando el grafo para resolver "qué hay cerca de
qué" en vez de reimplementar cálculo de distancias en el asistente.

**Por qué esta combinación y no otra**: el grafo ya tiene, cargado y
verificado, exactamente lo que hace falta:
- Nodos `:Lugar` (aparcamientos, cines, POIs — 381 nodos).
- Nodos `:EstacionMedida {tipo: "trafico"}` (4738 de los 4738+ totales,
  `id` con el formato `"trafico:<point_id>"` — el `point_id` sin el
  prefijo es la clave real de `gold.trafico_por_punto_hora`).
- La relación `:PROXIMO_A {distancia_m}` entre ambos tipos, ya calculada
  con un umbral de 300m (tarea 070) — no hay que recalcular proximidad
  aquí, solo consultarla.

`gold.trafico_por_punto_hora` (columnas reales: `point_id`, `subarea`,
`hour`, `avg_intensity_vph`, `avg_occupancy_ratio`, `avg_load_ratio`,
`avg_intensity_ratio`, `avg_service_level`, `lat`, `lon`, partición
`date`) es el dataset más maduro y verificado del proyecto (piloto
original, tarea 041) — candidato natural para la primera tool que cruza
grafo + Gold.

Credenciales de Neo4j en SSM (`/madrono-tfm/dev/secrets/neo4j-{uri,username,
password,database}`), mismo patrón que la tarea 080. `asistente/` es
deliberadamente autocontenido (no importa `grafo/`, ver docstring de
`asistente/athena.py`) — esta tarea necesita su propio cliente de lectura
de Neo4j dentro de `asistente/`, no reutilizar `grafo/cypher.py` (que solo
tiene métodos de escritura/carga, pensados para `cargar_grafo.py`, no para
consultas de lectura del servicio).

## Objetivo

Implementar `trafico_cercano(lugar, radio_m=300.0, momento=None)`: resuelve
`lugar` a un nodo `:Lugar` del grafo, sigue `PROXIMO_A` hasta las
`EstacionMedida` de tráfico dentro de `radio_m`, y consulta
`gold.trafico_por_punto_hora` para el estado real de esas estaciones.

## Alcance concreto

1. `asistente/neo4j_client.py` (nuevo): cliente de lectura mínimo, mismo
   nivel de autocontención que `asistente/athena.py` (credenciales de
   `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` vía
   variables de entorno — no las obtengas de SSM directamente desde este
   módulo, eso es responsabilidad del proceso que arranca el servicio,
   mismo patrón que `grafo/cargar_grafo.py::main()`). Añade el driver
   oficial `neo4j` a `asistente/requirements.txt` si no está ya.
2. `asistente/models/herramientas.py`: añade el modelo de retorno
   `TraficoCercano` (o similar) — lugar consultado, lista de estaciones
   encontradas (cada una con `point_id`, `distancia_m`,
   `avg_intensity_vph`/`avg_occupancy_ratio`/`avg_service_level` más
   recientes), y un resumen (p.ej. "congestionado"/"fluido"/"sin datos").
3. `asistente/mcp_agent/tools.py`: implementa `trafico_cercano(lugar,
   radio_m=300.0, momento=None)`:
   - Resuelve `lugar` contra `:Lugar` en el grafo por coincidencia de texto
     sobre su nombre (mismo criterio pragmático que `calidad_aire` usó para
     `zona` — no hace falta geocodificación libre en esta tarea).
   - Si no hay ningún `:Lugar` que coincida, o ninguna `EstacionMedida` de
     tráfico dentro de `radio_m`: no lances una excepción, devuelve un
     resultado explícito de "sin datos" (mismo criterio que `calidad_aire`).
   - Para las estaciones encontradas, extrae el `point_id` real del `id`
     del nodo (`"trafico:4260"` → `"4260"`) y consulta
     `gold.trafico_por_punto_hora` (vía `asistente/athena.py`, reutiliza el
     mecanismo ya existente) filtrando por esos `point_id` y por la fecha/
     hora de `momento` (o la más reciente disponible si es `None`).
4. Router HTTP nuevo (`asistente/routers/`, mismo patrón que
   `calidad_aire.py` de la tarea 079) que exponga esta tool vía HTTP.
5. Regístrala en `asistente/mcp_agent/server.py` junto a `calidad_aire`.
6. Tests: mockea tanto Neo4j (driver) como Athena — sin conexión real en
   los tests, mismo criterio que `grafo/tests/test_extract.py` y los tests
   de la tarea 079.
7. Verifica con al menos una invocación real (arranca el servicio local,
   consulta contra un lugar real del grafo — p.ej. un aparcamiento o cine
   ya cargado, revisa `MATCH (l:Lugar) RETURN l.nombre LIMIT 20` contra la
   instancia real para elegir uno existente) que la respuesta combina datos
   reales de Neo4j y de Athena, citando ambas fuentes.

## Restricciones

- Alcance: **solo esta tool nueva** — no toques `calidad_aire` (tarea 079)
  ni implementes las otras 4 `tools` con `NotImplementedError`.
- No implementes geocodificación de texto libre ni resolución de
  direcciones — la resolución de `lugar` es por coincidencia de texto
  sobre el nombre del nodo, igual que `calidad_aire` con `zona`.
- No modifiques `grafo/` — si necesitas una consulta de lectura, escríbela
  en el nuevo `asistente/neo4j_client.py`, no reutilices ni amplíes
  `grafo/cypher.py`.
- No despliegues nada (sin infraestructura Terraform nueva, mismo criterio
  que la tarea 044/079) — esta tarea es sobre el código del servicio.
- **Antes de terminar, confirma que dejas un commit real**, aunque la
  verificación no sea perfecta — documenta el resultado real de la
  invocación de prueba.

## Criterios de aceptación

- `trafico_cercano` devuelve datos reales combinando una consulta Cypher
  real al grafo y una consulta Athena real a Gold, verificado con al menos
  una invocación real contra un lugar real ya cargado en el grafo.
- Tests en verde, con Neo4j y Athena mockeados en la lógica unitaria.
- `asistente/README.md` actualizado: refleja que ya hay dos tools reales
  (`calidad_aire`, `trafico_cercano`) y que esta última es la primera que
  cruza datasets vía el grafo.
