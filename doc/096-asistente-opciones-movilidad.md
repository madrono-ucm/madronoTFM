# 096 — Asistente: implementar `opciones_movilidad`, última tool de la Prioridad 4

## Contexto

Última `tool` pendiente de las 6 originales del esqueleto de la tarea 044
(Prioridad 4 de `NEXT_STEPS.md`). A diferencia de las 5 anteriores,
`opciones_movilidad` no puede reutilizar directamente el patrón "resolver
un `:Lugar` + seguir `PROXIMO_A` + consultar Gold": su docstring original
proponía cruzar `origen`/`destino` contra la red viaria/de transporte
(`callejero_madrid`, `crtm_red_transporte_madrid`) para calcular rutas
reales. Investigado antes de implementar: el grafo **no tiene ningún grafo
de calles transitable** -- `CONECTADO_CON` (tarea 071) solo conecta paradas
de transporte público a lo largo de una misma línea CRTM (adyacencia de
red de transporte, no de calles/aceras entre dos puntos cualesquiera). Un
routing real punto a punto habría exigido construir un motor de
pathfinding desde cero, muy por encima del alcance de las 5 `tools`
anteriores.

**Decisión, confirmada con el usuario antes de implementar**: simplificación
deliberada y documentada, no routing real. `opciones_movilidad` resuelve
`origen`/`destino` por separado (mismo patrón `resolver_lugar_query` que
`eventos_cercanos`, tarea 095) y describe, para tres modos, las condiciones
reales encontradas cerca de cada extremo -- sin calcular ninguna ruta ni
duración. `duracion_estimada_min` (ya existente en el modelo `OpcionMovilidad`
del esqueleto de la tarea 044) queda siempre en `None`, documentado
explícitamente como limitación real, no fabricada.

## Qué se hizo

- `asistente/neo4j_client.py::lugares_proximos_a_paradas_emt_query`: nueva,
  igual que `lugares_proximos_a_paradas_bicimad_query` pero contra
  `ParadaTransporte {tipo: 'emt'}`.
- `asistente/mcp_agent/tools.py`: tres helpers reutilizados dos veces cada
  uno (origen y destino) -- `_trafico_cerca` (clasificación de tráfico,
  reutiliza `_clasificar_trafico`), `_bicimad_cerca` (bicis disponibles en
  el origen, anclajes libres en el destino -- **no el mismo campo en los
  dos extremos**, decisión deliberada: hacen falta bicis para coger en el
  origen, sitio donde dejarla en el destino), `_emt_cerca` (minutos hasta
  la próxima llegada estimada, el mejor caso entre las paradas cercanas).
  `_opciones_movilidad_impl` los combina en 3 `OpcionMovilidad` (`coche`,
  `transporte_publico`, `bicimad`), siempre las 3 si al menos uno de los
  dos puntos resuelve contra el grafo.
- `asistente/routers/opciones_movilidad.py`: nuevo, `GET /opciones-movilidad`
  -- mismo caso que `eventos_cercanos.py` (la tool devuelve una lista, no un
  único modelo con `fuente_dataset`).
- Registrado en `main.py` y ya estaba registrado en `mcp_agent/server.py`
  desde la tarea 044.
- Tests: `test_opciones_movilidad.py` (4 casos) con `_RoutingNeo4jDriver`/
  `_RoutingAthenaClient` propios -- ninguno de los dobles existentes
  (`FakeNeo4jDriver`, ni siquiera el de `test_afluencia_estimada.py`)
  soporta enrutar por **combinación de lugar y tipo** (esta tool consulta
  el mismo tipo de nodo dos veces, una por cada punto, con resultados
  distintos) -- se construyeron dobles nuevos que enrutan Neo4j por
  `nombre_lugar`+`tipo` y Athena por tabla, filtrando filas por los IDs
  literales presentes en el SQL real. + `test_opciones_movilidad_router.py`
  (2 casos).

## Verificación real

Arrancado el servicio real con credenciales de Neo4j (SSM) y la cuenta AWS
del proyecto:

- `GET /opciones-movilidad?origen=Retiro&destino=Sol` → 3 opciones con
  datos reales y distintos en cada extremo:
  - `coche`: tráfico fluido cerca de origen y destino.
  - `bicimad`: 8.0 bicis de media cerca del origen, 15.1 anclajes libres de
    media cerca del destino.
  - `transporte_publico`: "sin datos" en ambos extremos -- consistente con
    la cobertura real muy limitada de `transporte_publico_emt` (1 solo
    `stop_id` real distinto en Gold, `NEXT_STEPS.md` Prioridad 7),
    documentada explícitamente en el docstring de `_emt_cerca` antes de
    verificar, no descubierta a posteriori.
- `GET /opciones-movilidad?origen=<inexistente>&destino=<inexistente>` →
  `fiabilidad="baja"`, `fuentes=[]`, sin excepción.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform.
- No se ha intentado ningún routing real por calles -- explícitamente fuera
  de alcance hasta que exista un grafo de calles transitable.
- Servicio local (`uvicorn`) parado al terminar la verificación.

## Relevante para tareas futuras

- Las 6 `tools` originales del esqueleto de la tarea 044 ya tienen lógica
  real -- Prioridad 4 de `NEXT_STEPS.md` queda completa.
- Si se quiere routing real en el futuro: hace falta primero un grafo de
  calles transitable a partir de `callejero_madrid` (nodos por tramo/cruce,
  adyacencia real entre tramos) -- `CONECTADO_CON` (tarea 071) no sirve
  para esto, solo conecta paradas de transporte público a lo largo de una
  línea.
- Sigue pendiente (ya señalado en la tarea 095) repetir la verificación
  completa de `trafico_cercano`/`afluencia_estimada` contra Neo4j real
  ahora que las credenciales están disponibles.
