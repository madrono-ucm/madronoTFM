---
id: 67
slug: etl-grafo-neo4j-nodos
title: ETL de carga de nodos del grafo Neo4j (sin conexión real, sigue bloqueado)
status: in_review
force: true
allow_infra_apply: false
branch: task/067-etl-grafo-neo4j-nodos
pr_number: 114
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/114
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-20T09:00:00+00:00'
updated_at: '2026-08-20T21:51:21.881970+00:00'
started_at: '2026-08-20T21:43:20.625633+00:00'
submitted_at: '2026-08-20T21:51:21.881825+00:00'
merged_at: null
---

## Contexto

La tarea 043 decidió el motor (Neo4j AuraDB Free), diseñó el esquema
(`infra/neo4j/schema/schema.cypher`: nodos `:Distrito`, `:Barrio`,
`:Lugar`, `:EstacionMedida`, `:ParadaTransporte`; relaciones
`PERTENECE_A`, `UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`) y documentó que
crear la instancia real requiere un alta manual en
`https://console.neo4j.io` (mismo tipo de bloqueo que EMT/AEMET/CAMS/Google
Maps) — **sigue sin existir ninguna instancia real, este bloqueo no lo
resuelve esta tarea**.

Con Silver/Gold ya en producción continua (tareas 041-065) para los 14
datasets operativos, esta tarea escribe el ETL que transformaría esos datos
(más las fuentes de referencia estática que nunca pasaron por Silver/Gold:
`barrios_distritos_madrid`, `poi_madrid`, `crtm_red_transporte_madrid`,
`callejero_madrid` — siguen siendo solo Bronze) en los nodos del grafo —
**código puro, testado con fixtures, sin conectar a ninguna instancia
real, igual que se hizo con `procesamiento/silver_gold/` antes de que
existiera la infraestructura de Glue.**

**Alcance acotado a propósito, no lo amplíes**: esta tarea es solo **nodos**
(los 4 tipos) y la relación `PERTENECE_A` (Barrio→Distrito, un simple
lookup por código de distrito, sin geometría). Las otras 3 relaciones
(`UBICADO_EN`, point-in-polygon; `PROXIMO_A`, proximidad genérica;
`CONECTADO_CON`, adyacencia real de red de transporte) son tareas de
seguimiento separadas — no las implementes aquí aunque te parezca poco
esfuerzo adicional.

## Objetivo

Escribir la lógica de extracción/transformación (Python puro, testable) que
produce, para cada uno de los 4 tipos de nodo del esquema, los registros
listos para cargar en Neo4j (como `dict`, con las propiedades que definió
`schema.cypher`), más los pares `PERTENECE_A`.

## Alcance concreto

1. Directorio nuevo `grafo/` (análogo de `ingesta/`/`procesamiento/` para
   esta pieza; sigue el mismo patrón de estructura y de README que ambos).
2. `grafo/nodos.py` (Python puro, sin driver de Neo4j como dependencia de
   import): funciones que, dado un registro Gold/Bronze normalizado, lo
   convierten al `dict` de propiedades de cada tipo de nodo:
   - `:Distrito`/`:Barrio` — desde `barrios_distritos_madrid` (Bronze, el
     único origen, no tiene Silver/Gold).
   - `:EstacionMedida` — desde Gold de `trafico`, `calidad_aire`, `ruido`
     (un nodo por punto/estación única, no por cada fila horaria — dedup
     por `point_id`/`station_id`).
   - `:ParadaTransporte` — desde Gold de `transporte_publico_emt`,
     `bicimad`, y Bronze de `crtm_red_transporte_madrid` (sin Silver/Gold).
   - `:Lugar` — desde Gold de `aparcamientos`, `cartelera_cines_estrenos`,
     y Bronze de `poi_madrid` (sin Silver/Gold), con `tipo` como
     discriminador (ver `schema.cypher`).
3. `grafo/relaciones.py`: `PERTENECE_A` (Barrio→Distrito), un simple
   lookup por el código de distrito que ya trae `barrios_distritos_madrid`
   — sin cálculo geométrico.
4. `grafo/cypher.py`: capa fina que traduce esos `dict` a sentencias
   `MERGE`/`CREATE` de Cypher parametrizadas (usa `MERGE` sobre la clave
   `constraint`/`UNIQUE` de `schema.cypher` para que cargar dos veces no
   duplique nodos) — este módulo sí puede asumir el driver oficial
   `neo4j` como dependencia (añádela a un `grafo/requirements.txt` nuevo),
   pero **no lo importes desde `nodos.py`/`relaciones.py`** (mismo patrón
   de separación lógica-pura/adaptador que `procesamiento/`).
5. Tests en `grafo/tests/` con fixtures pequeñas tomadas de las muestras ya
   commiteadas (`ingesta/capturas/samples/`, `procesamiento/tests/
   fixtures/`) — sin necesidad de una instancia Neo4j real, sin instalar el
   driver `neo4j` para los tests de `nodos.py`/`relaciones.py`.
6. `grafo/README.md`: documenta la estructura, qué falta (las 3 relaciones
   restantes, la instancia real) y cómo se cargaría el día que exista
   `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` (ya documentadas en
   `infra/neo4j/README.md`, tarea 043 — no las redefinas, referencia ese
   fichero).

## Restricciones

- NO intentes crear ni conectar a ninguna instancia real de Neo4j — sigue
  bloqueado en el alta manual de la tarea 043.
- NO implementes `UBICADO_EN`/`PROXIMO_A`/`CONECTADO_CON` — son tareas de
  seguimiento separadas, mantener el alcance pequeño es lo que ha evitado
  repetir los fallos por presupuesto agotado de tareas anteriores similares
  (055/057).
- NO instales el driver `neo4j` en esta EC2 más allá de lo que
  `grafo/requirements.txt` declare (no hace falta para los tests, ver
  arriba).
- No toques `infra/neo4j/schema/schema.cypher` salvo que encuentres un
  error real en él — si lo haces, documenta por qué.

## Criterios de aceptación

- `grafo/nodos.py`/`relaciones.py` producen los 4 tipos de nodo + `PERTENECE_A`
  a partir de datos reales (Gold/Bronze ya commiteados), con tests en verde.
- `grafo/cypher.py` genera sentencias `MERGE` correctas (verificable por
  inspección/test de la cadena generada, sin conexión real).
- `grafo/README.md` documenta el estado y los próximos pasos.
