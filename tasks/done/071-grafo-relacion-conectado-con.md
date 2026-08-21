---
id: 71
slug: grafo-relacion-conectado-con
title: 'Grafo: relación CONECTADO_CON (adyacencia real de la red de transporte)'
status: done
force: true
allow_infra_apply: false
branch: task/071-grafo-relacion-conectado-con
pr_number: 118
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/118
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-21T09:30:00+00:00'
updated_at: '2026-08-21T21:00:01.357263+00:00'
started_at: '2026-08-21T20:51:05.727409+00:00'
submitted_at: '2026-08-21T20:58:58.696020+00:00'
merged_at: '2026-08-21T20:58:31Z'
---

## Contexto

Última relación pendiente del esquema del grafo (`schema.cypher`, tarea
043): `CONECTADO_CON`, adyacencia real de la red de transporte (con
`modo`/`linea` como propiedades, lo que hace de `:ParadaTransporte` un
grafo navegable — p.ej. para responder "¿qué paradas conectan directamente
con esta?"). Deliberadamente separada de la tarea 070 (relaciones
espaciales) porque su fuente y su lógica son distintas: no es proximidad
geométrica, es la secuencia real de paradas de cada línea.

`crtm_red_transporte_madrid` (Bronze, ver
`ingesta/capturas/samples/crtm_red_transporte_madrid_sample.json`) trae,
por cada `route_id` (línea), una lista `stops` **ya ordenada por
`sequence`** — dos paradas consecutivas en esa lista están conectadas
directamente por esa línea.

**Decisión ya tomada (no la reabras)**: `CONECTADO_CON` se genera **solo**
a partir de pares consecutivos dentro de la misma `route_id` (no
infieras conexiones entre líneas distintas aunque compartan estación física
— eso ya lo cubre `PROXIMO_A` de la tarea 070 si están dentro del umbral de
300m). La relación es dirigida en el sentido de `sequence` creciente, pero
crea también el sentido inverso (mismo `route_id`, mismo `modo`) salvo que
el propio dataset indique que la línea es de sentido único — revísalo en
el fixture real antes de asumir bidireccionalidad.

## Objetivo

Añadir a `grafo/relaciones.py` la función que genera `CONECTADO_CON` a
partir de las rutas de `crtm_red_transporte_madrid`.

## Alcance concreto

1. `grafo/relaciones.py`: `conectado_con(rutas_crtm)` — para cada
   `route_id`, recorre `stops` ordenados por `sequence` y genera una
   relación `CONECTADO_CON` (`modo`, `linea` = `short_name`/`route_id`)
   entre cada par consecutivo.
2. Los `stop_id` de CRTM deben casar con los `:ParadaTransporte` ya creados
   por `nodos.py` (tarea 067) — si algún `stop_id` de una ruta no tiene
   nodo correspondiente (p.ej. viene de un modo no cubierto por
   `nodos.py` todavía), créalo igualmente como `:ParadaTransporte` mínimo
   (id + nombre + ubicación) en vez de descartar la relación, y documenta
   esta decisión.
3. Tests en `grafo/tests/test_relaciones.py` (ampliar) con el fixture real
   de `crtm_red_transporte_madrid_sample.json` — verifica el número de
   relaciones generadas para al menos una ruta conocida del fixture.
4. Actualiza `grafo/cargar_grafo.py` (tarea 069) para incluir esta relación.
5. Actualiza `grafo/README.md`.

## Restricciones

- NO generes `CONECTADO_CON` entre líneas distintas ni por proximidad
  física — solo adyacencia real dentro de la misma `route_id`, ver arriba.
- NO conectes a ninguna instancia real de Neo4j.

## Criterios de aceptación

- `relaciones.py` genera `CONECTADO_CON` correctamente a partir de datos
  reales de CRTM, verificado con tests.
- `grafo/README.md` actualizado.
