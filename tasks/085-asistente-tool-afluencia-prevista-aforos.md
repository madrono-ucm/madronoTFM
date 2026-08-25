---
id: 85
slug: asistente-tool-afluencia-prevista-aforos
title: 'Asistente: implementar afluencia_prevista sobre aforos (sin Google)'
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: null
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

**Depende de la tarea `084` ya fusionada** — necesita `:EstacionMedida
{tipo: "aforo"}` y sus relaciones `PROXIMO_A` cargadas en la instancia real
de Neo4j. No la empieces si `084` sigue pendiente.

`afluencia_prevista(lugar, momento=None)` levanta hoy `NotImplementedError`
(ver su docstring en `asistente/mcp_agent/tools.py`): estaba pensada contra
`populartimes`/Google Places (`GOOGLE_MAPS_API_KEY`, no disponible en este
entorno). Decisión tomada: en vez de esperar esa credencial, se responde
con una señal real y gratuita ya en producción —
`gold.aforos_peatones_bicicletas_por_estacion_modo_hora` (conteos horarios
de peatones/bicicletas, tarea 054) cruzada con el grafo, **exactamente el
mismo patrón que `trafico_cercano`** (tarea 081, primera tool que cruza
Neo4j + Athena) pero contra `EstacionMedida {tipo: 'aforo'}` en vez de
`'trafico'`.

Esto es un cambio de significado, no solo de fuente: en vez de "popularidad
estimada de un lugar concreto" (lo que ofrecía Google), la respuesta pasa a
ser "afluencia peatonal/ciclista medida cerca de ese lugar" — una señal
real distinta, no una imitación de la de Google. Documenta este cambio de
alcance explícitamente en el docstring y en `asistente/README.md`, no lo
dejes implícito.

Revisa `asistente/mcp_agent/tools.py::trafico_cercano`/`_trafico_cercano_impl`
y `asistente/neo4j_client.py::lugares_proximos_a_estaciones_trafico_query`
como plantilla exacta a replicar.

## Objetivo

Implementar `afluencia_prevista(lugar, radio_m=300.0, momento=None)`:
resuelve `lugar` a `:Lugar`, sigue `PROXIMO_A` hasta `EstacionMedida {tipo:
'aforo'}` dentro de `radio_m`, y consulta
`gold.aforos_peatones_bicicletas_por_estacion_modo_hora` para el conteo más
reciente de esas estaciones.

## Alcance concreto

1. `asistente/neo4j_client.py`: añade
   `lugares_proximos_a_estaciones_aforo_query(nombre_lugar, radio_m)`,
   calcada de `lugares_proximos_a_estaciones_trafico_query` cambiando el
   filtro a `tipo: 'aforo'`.
2. `asistente/models/herramientas.py`: rediseña `AfluenciaPrevista` sobre el
   mismo patrón que `TraficoCercano`/`EstacionTraficoCercana` (que no
   existían cuando se escribió el modelo original de `AfluenciaPrevista`,
   tarea 044): lista de estaciones de aforo cercanas (`station_id`,
   `distancia_m`, `mode`, `total_count`/`avg_count` más recientes,
   opcionales por la misma razón que documenta
   `EstacionTraficoCercana`: el grafo puede encontrar una estación sin que
   Gold tenga fila para esa fecha/hora), más un resumen simplificado
   (`nivel_ocupacion`: p.ej. `"bajo"`/`"medio"`/`"alto"`/`"sin_datos"` —
   documenta el criterio de los umbrales igual que
   `_UMBRALES_SERVICE_LEVEL`/`_UMBRALES_OCCUPANCY_RATIO` en
   `trafico_cercano`, no hay escala oficial así que dejar el criterio
   explícito en un comentario es importante). Actualiza el docstring de la
   clase para reflejar que ya no viene de Google/`populartimes`.
3. `asistente/mcp_agent/tools.py::afluencia_prevista`: implementa siguiendo
   `_trafico_cercano_impl` como plantilla — resolución de `lugar` por texto
   igual que `calidad_aire`/`trafico_cercano`, agregación por `station_id`
   con la distancia mínima real cuando se repite, consulta a Athena
   filtrando por `date`/`hour` de `momento` (o el más reciente si es
   `None`), devuelve resultado explícito de "sin datos" si no hay `:Lugar`
   o ninguna estación de aforo dentro del radio (no lances excepción).
4. Regístrala junto a `calidad_aire`/`trafico_cercano` en
   `asistente/mcp_agent/server.py` si no lo está ya (revisa si `044` ya la
   registró con el modelo antiguo).
5. Router HTTP nuevo en `asistente/routers/`, mismo patrón que
   `trafico_cercano.py`.
6. Tests: mockea Neo4j y Athena, mismo criterio que
   `asistente/tests/test_neo4j_client.py`/`test_mcp_tools.py` para
   `trafico_cercano`. Añade también un test de router HTTP, mismo patrón
   que `asistente/tests/test_trafico_cercano_router.py`.
7. Verifica con al menos una invocación real contra la instancia real de
   Neo4j + Athena (un `:Lugar` real cercano a alguna estación de aforo ya
   cargada por la tarea `084` — confírmalo con
   `MATCH (l:Lugar)-[:PROXIMO_A]-(:EstacionMedida {tipo:'aforo'}) RETURN
   l.nombre LIMIT 20` antes de elegir uno).

## Restricciones

- Alcance: solo `afluencia_prevista` — no toques `calidad_aire` ni
  `trafico_cercano`, ni las otras dos `tools` con `NotImplementedError`.
- No reactives `ingesta/capturas/afluencia_lugares_madrid.py`
  (`populartimes`/Google) — queda como está, documentada como fuente no
  usada por la tool real (aclara esto en `asistente/README.md` para que no
  se asuma que sigue siendo la fuente).
- No implementes geocodificación libre — resolución de `lugar` por
  coincidencia de texto, igual que las otras tools.
- No modifiques `grafo/` en esta tarea — si la tarea `084` no dejó algo que
  necesitas, para y documenta el bloqueo en vez de ampliar `grafo/` aquí.

## Criterios de aceptación

- `afluencia_prevista` devuelve datos reales combinando una consulta
  Cypher real (`EstacionMedida {tipo: 'aforo'}`) y una consulta Athena real
  a `gold.aforos_peatones_bicicletas_por_estacion_modo_hora`, verificado con
  al menos una invocación real.
- `PLAN.md`: marca el bloqueador de la clave de Google Maps como resuelto
  para `afluencia_prevista` específicamente (sigue pudiendo quedar como
  posible mejora futura, pero ya no bloquea esta tool).
- Tests en verde.
- `asistente/README.md` actualizado: tres tools reales
  (`calidad_aire`, `trafico_cercano`, `afluencia_prevista`), y aclara que
  esta última usa `aforos_peatones_bicicletas`, no Google.
