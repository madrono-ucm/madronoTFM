---
id: 89
slug: asistente-tool-afluencia-estimada
title: 'Asistente: Fase B de la especificación 086 -- implementar afluencia_estimada'
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

**Depende de la tarea `087` ya fusionada** (Fase A: necesita
`:EstacionMedida {tipo: "aforos_peatones_bicicletas"}` y sus relaciones
`PROXIMO_A` cargadas en la instancia real). No la empieces si `087` sigue
pendiente.

**Esta tarea implementa la "Fase B" de `doc/086-afluencia-estimada-grafo.md`
(tarea 086) -- léela entera antes de empezar, es la fuente de verdad del
diseño.** En particular, respeta estas dos decisiones ya tomadas que un
diseño anterior propio no tenía:

- **La tool se llama `afluencia_estimada`, no `afluencia_prevista`** --
  `afluencia_prevista` (nombre del esqueleto original, tarea 044) sugería
  previsión temporal tipo Google (`typical_by_hour`); esta tool da un
  estado estimado del momento consultado a partir de sensores reales, no
  una previsión estadística. Sustituye la entrada `afluencia_prevista` en
  `asistente/mcp_agent/tools.py` y en la tabla de `asistente/README.md`.
- **Combina varias señales, no solo aforos**: `aforos_peatones_bicicletas`
  (primaria) + `:ParadaTransporte {tipo: "bicimad"}` (ocupación) +
  `:EstacionMedida {tipo: "trafico"}` (intensidad, reutilizando la consulta
  que ya usa `trafico_cercano` -- no la dupliques) como señales
  secundarias, dentro del mismo `radio_m`. Si `aparcamientos` (Prioridad 2
  de `NEXT_STEPS.md`) ya está arreglado cuando implementes esto, añade su
  ocupación como cuarta señal; si no, omítela sin error.

`agenda_eventos`/`agenda_recintos` quedan **fuera de alcance** (no están en
el grafo, añadirlos sería una tercera fase) -- si `momento` cae cerca de un
evento conocido, no lo detectes aquí; simplemente no lo menciones como
señal disponible.

Revisa `asistente/mcp_agent/tools.py::trafico_cercano`/`_trafico_cercano_impl`
y `asistente/neo4j_client.py::lugares_proximos_a_estaciones_trafico_query`
como plantilla de estructura (resolución de `lugar` por texto, agregación
por estación con distancia mínima, resultado explícito de "sin datos").

## Objetivo

Implementar `afluencia_estimada(lugar, radio_m=300.0, momento=None)` según
la Fase B de `doc/086-afluencia-estimada-grafo.md`.

## Alcance concreto

1. `asistente/neo4j_client.py`: añade la consulta de proximidad a
   `EstacionMedida {tipo: "aforos_peatones_bicicletas"}` (calcada de
   `lugares_proximos_a_estaciones_trafico_query`), y reutiliza/factoriza la
   ya existente para `trafico` en vez de duplicarla si hace falta llamarla
   desde aquí también.
2. `asistente/models/herramientas.py`: rediseña el modelo de retorno
   (renómbralo si `AfluenciaPrevista` sigue con ese nombre) para reflejar
   la combinación de señales: lista de estaciones de aforos cercanas
   (`station_id`, `distancia_m`, `mode`, `total_count`/`avg_count` --
   opcionales, mismo criterio que `EstacionTraficoCercana` cuando Gold no
   tiene fila para esa fecha/hora), señales secundarias (BiciMAD, tráfico)
   y un resumen simplificado `nivel_estimado`
   (`"bajo"`/`"medio"`/`"alto"`/`"sin_datos"`, con el criterio de los
   umbrales documentado explícitamente -- no hay escala oficial).
3. `asistente/mcp_agent/tools.py`: implementa `afluencia_estimada(lugar,
   radio_m=300.0, momento=None)` -- resolución de `lugar` por texto igual
   que las otras tools, agregación por estación con la distancia mínima
   real cuando se repite, consulta a Athena por `date`/`hour` de `momento`
   (o el más reciente si es `None`), resultado explícito de "sin datos" si
   no hay `:Lugar` o ninguna estación de aforos dentro del radio.
4. Sustituye la entrada `afluencia_prevista` por `afluencia_estimada` en
   `asistente/mcp_agent/server.py`.
5. Router HTTP nuevo en `asistente/routers/`, mismo patrón que
   `trafico_cercano.py`.
6. Tests: mockea Neo4j y Athena, mismo criterio que los tests existentes de
   `trafico_cercano`. Añade test de router HTTP.
7. Verifica con al menos una invocación real contra la instancia real
   (Neo4j + Athena) -- confirma primero con Cypher real que existe un
   `:Lugar` cercano a alguna estación de aforos ya cargada por la tarea
   `087`.

## Restricciones

- Alcance: solo `afluencia_estimada` -- no toques `calidad_aire` ni
  `trafico_cercano`, ni las otras `tools` con `NotImplementedError`.
- No implementes `agenda_eventos`/`agenda_recintos` como señal -- fuera de
  alcance (ver Contexto).
- No reactives `ingesta/capturas/afluencia_lugares_madrid.py`/
  `populartimes`.
- No modifiques `grafo/` -- si la tarea `087` no dejó algo que necesitas,
  para y documenta el bloqueo en vez de ampliar `grafo/` aquí.

## Criterios de aceptación

- `afluencia_estimada` devuelve datos reales combinando al menos la señal
  primaria (`aforos_peatones_bicicletas` vía grafo + Athena) con una
  invocación real verificada.
- `PLAN.md`/`asistente/README.md`: marcan `afluencia_estimada` como
  implementada, y que el bloqueador de la clave de Google Maps queda
  completamente cerrado (ninguna tool depende ya de él).
- Tests en verde.
