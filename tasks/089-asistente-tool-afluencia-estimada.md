---
id: 89
slug: asistente-tool-afluencia-estimada
title: 'Asistente: implementar afluencia_estimada (redisenada tras el hallazgo de
  la tarea 087)'
status: blocked
force: false
allow_infra_apply: false
branch: task/089-asistente-tool-afluencia-estimada
pr_number: null
pr_url: null
attempts: 3
next_retry_at: '2026-08-25T22:15:00.398329+00:00'
last_error: You've hit your session limit · resets 1:20am (UTC)
created_at: null
updated_at: '2026-08-25T21:54:29.603318+00:00'
started_at: '2026-08-25T21:25:46.675284+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Esta tarea sustituye por completo el diseño original de la Fase B de
`doc/086-afluencia-estimada-grafo.md`** — lee primero la corrección al
principio de `doc/086-...md` y `doc/087-grafo-aforos-peatones-bicicletas-
neo4j-real.md` (sección "Corrección 25/8"): `aforos_peatones_bicicletas`
(la señal primaria del diseño original) resultó ser una fuente externa
**descontinuada desde el 30/6/2024** (verificado contra Athena real y de
forma independiente contra `datos.madrid.es`), no un dataset sano en
producción como se asumió al escribir la tarea 086. No es un bug de este
proyecto — es la fuente municipal la que dejó de publicar.

**Diseño nuevo, decidido con el usuario el 25/8**: `afluencia_estimada`
combina cuatro señales con datos reales y frescos, **todas ya verificadas
contra Athena real en esta sesión** (ver `grafo/README.md`, "Verificado
contra datos reales"):

- `:EstacionMedida {tipo: "trafico"}` — intensidad/ocupación vial
  (`gold.trafico_por_punto_hora`, 4678 filas reales).
- `:EstacionMedida {tipo: "ruido"}` — nivel de ruido
  (`gold.ruido_por_estacion_periodo_fecha`, 31 filas reales,
  `avg_laeq_db`).
- `:ParadaTransporte {tipo: "bicimad"}` — ocupación de estaciones BiciMAD
  (`gold.bicimad_por_estacion_hora`, `avg_occupancy_ratio`/
  `avg_bikes_available`/`avg_docks_available`).
- `:EstacionMedida {tipo: "calidad_aire"}` — señal más débil/indirecta
  (correlaciona con congestión, no con afluencia peatonal directamente),
  inclúyela como cuarta señal opcional, no bloqueante si falta.

Ninguna de las cuatro mide peatones directamente (a diferencia de lo que
habría dado `aforos_peatones_bicicletas` si hubiera tenido datos reales) —
documenta esta limitación explícitamente en el docstring de la tool y en
`nivel_estimado`: es una aproximación por actividad urbana general
(tráfico/ruido/movilidad), no un conteo de personas.

**No borres el código de la tarea 087** (`grafo/extract.py::fetch_estaciones_
aforos_peatones_bicicletas`, `grafo/nodos.py::estacion_medida_from_aforos_
peatones_bicicletas_gold`, etc.) — queda listo por si la fuente externa
vuelve a publicar en el futuro, simplemente no lo uses en esta tool.

Revisa `asistente/mcp_agent/tools.py::trafico_cercano`/`_trafico_cercano_impl`
y `asistente/neo4j_client.py::lugares_proximos_a_estaciones_trafico_query`
como plantilla de estructura (resolución de `lugar` por texto, agregación
por estación con distancia mínima, resultado explícito de "sin datos").
`trafico_cercano` ya expone la consulta de proximidad a `tipo: "trafico"` —
reutilízala (no la dupliques).

## Objetivo

Implementar `afluencia_estimada(lugar, radio_m=300.0, momento=None)`:
combina tráfico + ruido + BiciMAD (+ calidad del aire si está disponible)
cerca de `lugar`, vía el grafo, en una estimación simplificada de actividad
urbana.

## Alcance concreto

1. `asistente/neo4j_client.py`: añade consultas de proximidad a
   `:EstacionMedida {tipo: "ruido"}` y `:ParadaTransporte {tipo: "bicimad"}`
   (calcadas de `lugares_proximos_a_estaciones_trafico_query`, cambiando
   solo el label/tipo filtrado). Reutiliza la de `trafico` y, si ya existe,
   la de `calidad_aire` (revisa `asistente/mcp_agent/tools.py::calidad_aire`
   antes de asumir que hace falta escribir una nueva).
2. `asistente/models/herramientas.py`: rediseña `AfluenciaPrevista` (o el
   nombre que tenga en ese momento) para reflejar las señales nuevas:
   listas de estaciones cercanas por tipo (`trafico`, `ruido`, `bicimad`,
   `calidad_aire`), cada una con `distancia_m` + su valor real más
   reciente (todo opcional, mismo criterio que `EstacionTraficoCercana`
   cuando Gold no tiene fila para esa fecha/hora), y un resumen
   `nivel_estimado` (`"bajo"`/`"medio"`/`"alto"`/`"sin_datos"`) con el
   criterio de los umbrales documentado explícitamente por señal (no hay
   escala oficial combinada -- normaliza cada señal a una etiqueta simple
   primero, mismo patrón que `_UMBRALES_SERVICE_LEVEL` de
   `trafico_cercano`, y combina las etiquetas resultantes, no los valores
   brutos de escalas distintas).
3. `asistente/mcp_agent/tools.py`: implementa `afluencia_estimada(lugar,
   radio_m=300.0, momento=None)` -- resolución de `lugar` por texto igual
   que las otras tools, agregación por estación con la distancia mínima
   real cuando se repite, consulta a Athena por `date`/`hour` de `momento`
   (o el más reciente si es `None`) para cada señal. Si ninguna señal tiene
   ninguna estación dentro del radio, resultado explícito de "sin datos"
   (no excepción). Si solo alguna de las cuatro señales tiene datos, calcula
   `nivel_estimado` con las que haya disponibles -- no falles por falta de
   una señal.
4. Sustituye la entrada `afluencia_prevista` por `afluencia_estimada` en
   `asistente/mcp_agent/server.py`.
5. Router HTTP nuevo en `asistente/routers/`, mismo patrón que
   `trafico_cercano.py`.
6. Tests: mockea Neo4j y Athena, mismo criterio que los tests existentes de
   `trafico_cercano`. Añade test de router HTTP, y casos de "solo alguna
   señal disponible" / "ninguna señal disponible".
7. Verifica con al menos una invocación real contra la instancia real
   (Neo4j + Athena) -- usa un `:Lugar` real conocido con estaciones de
   `trafico`/`ruido`/`bicimad` cerca (confírmalo con Cypher real antes de
   elegir uno).

## Restricciones

- Alcance: solo `afluencia_estimada` -- no toques `calidad_aire` ni
  `trafico_cercano`, ni las otras `tools` con `NotImplementedError`.
- No uses `aforos_peatones_bicicletas` como señal -- fuente descontinuada
  (ver Contexto), aunque el código de la tarea 087 siga en el repositorio.
- No implementes `agenda_eventos`/`agenda_recintos` como señal -- fuera de
  alcance, no están en el grafo.
- No reactives `ingesta/capturas/afluencia_lugares_madrid.py`/
  `populartimes`.
- No modifiques `grafo/`.

## Criterios de aceptación

- `afluencia_estimada` devuelve datos reales combinando al menos dos de
  las cuatro señales vía grafo + Athena, verificado con una invocación
  real.
- `PLAN.md`/`asistente/README.md`: marcan `afluencia_estimada` como
  implementada (señal compuesta tráfico/ruido/BiciMAD/calidad del aire, no
  aforos), y que el bloqueador de la clave de Google Maps queda
  completamente cerrado.
- Tests en verde.
