---
id: 70
slug: grafo-relaciones-espaciales
title: 'Grafo: relaciones espaciales UBICADO_EN y PROXIMO_A'
status: done
force: true
allow_infra_apply: false
branch: task/070-grafo-relaciones-espaciales
pr_number: 117
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/117
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-21T09:30:00+00:00'
updated_at: '2026-08-21T20:50:03.231072+00:00'
started_at: '2026-08-21T20:41:31.515751+00:00'
submitted_at: '2026-08-21T20:48:56.472705+00:00'
merged_at: '2026-08-21T20:49:00Z'
---

## Contexto

La tarea 041 y la 067 dejaron deliberadamente pendientes las relaciones
espaciales del grafo (`schema.cypher`, tarea 043): `UBICADO_EN`
(point-in-polygon de cualquier nodo con ubicación contra `:Barrio`) y
`PROXIMO_A` (proximidad genérica entre cualquier par de nodos con
ubicación). Esta tarea las implementa.

`barrios_distritos_madrid` (Bronze, ver
`ingesta/capturas/samples/barrios_distritos_madrid_barrios_sample.json`)
trae la geometría real de cada barrio como GeoJSON `Polygon`
(`geometry.coordinates`) — suficiente para point-in-polygon sin ninguna
dependencia nueva.

**Decisiones ya tomadas (no las reabras)**:
- **Point-in-polygon en Python puro** (algoritmo de ray casting sobre
  `geometry.coordinates`, sin `shapely` ni ninguna dependencia geométrica
  nueva) — mismo criterio que ya se usó para la reproyección de tráfico en
  la tarea 041 (fórmulas cerradas en vez de `pyproj`), evita el mismo tipo
  de fricción de despliegue que causó `netCDF4` en su día.
- **Umbral de `PROXIMO_A`: 300 metros** (distancia Haversine) entre
  cualquier par de nodos con ubicación de tipos distintos (no generes
  `PROXIMO_A` entre dos nodos del mismo tipo, ya se relacionan por su
  propia semántica — p.ej. dos `:EstacionMedida` de tráfico no necesitan
  `PROXIMO_A` entre sí). Si un nodo tiene decenas de vecinos dentro de ese
  radio (zonas muy densas del centro), no limites el número de relaciones
  generadas — es información real, no ruido a filtrar.

## Objetivo

Añadir a `grafo/relaciones.py` (ya existente, tarea 067) las funciones que
generan `UBICADO_EN` y `PROXIMO_A` a partir de los nodos ya extraídos.

## Alcance concreto

1. `grafo/geo.py` (nuevo, Python puro): point-in-polygon por ray casting
   (dado un punto `lat`/`lon` y una lista de polígonos de barrio, devuelve
   el `neighbourhood_id` que lo contiene, o `None` si no cae en ninguno —
   documenta qué haces con los `MultiPolygon` si `barrios_distritos_madrid`
   los tiene, revísalo en el fixture real) y distancia Haversine entre dos
   puntos.
2. `grafo/relaciones.py`: añade `ubicado_en(nodos_con_ubicacion, barrios)`
   (usa `geo.py`, un `UBICADO_EN` por nodo que caiga dentro de algún
   barrio) y `proximo_a(nodos_con_ubicacion, umbral_m=300)` (todas las
   parejas de tipos distintos dentro del umbral, con `distancia_m` como
   propiedad de la relación, ver `schema.cypher`).
3. Tests en `grafo/tests/test_geo.py` (casos conocidos: un punto real
   dentro de un barrio real del fixture, un punto claramente fuera de
   Madrid) y ampliar `grafo/tests/test_relaciones.py` con casos de
   `ubicado_en`/`proximo_a` sobre fixtures pequeñas construidas a mano.
4. Actualiza `grafo/cargar_grafo.py` (tarea 069) para incluir estas dos
   relaciones en la cadena extract→transform→cypher.
5. Actualiza `grafo/README.md`.

## Restricciones

- NO añadas `shapely` ni ninguna otra dependencia de geometría — Python
  puro, ver decisión arriba.
- NO implementes `CONECTADO_CON` aquí — es la tarea 071, alcance
  deliberadamente separado.
- NO conectes a ninguna instancia real de Neo4j.

## Criterios de aceptación

- `geo.py` calcula point-in-polygon y Haversine correctamente, verificado
  con datos reales de `barrios_distritos_madrid` en los tests.
- `relaciones.py` genera `UBICADO_EN`/`PROXIMO_A` con las propiedades que
  define `schema.cypher`.
- Tests en verde.
- `grafo/README.md` actualizado.
