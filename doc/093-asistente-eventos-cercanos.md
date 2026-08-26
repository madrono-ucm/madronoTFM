# 093 — Asistente: implementar `eventos_cercanos`, última pieza real de la Prioridad 4

## Contexto

Continuación de la tarea 091 (`disponibilidad_aparcamiento`): siguiente
`tool` pendiente de `NEXT_STEPS.md`, Prioridad 4. `eventos_cercanos` cruza
un lugar contra `agenda_eventos`, pero a diferencia de `trafico_cercano`/
`afluencia_estimada` (que siguen `PROXIMO_A` hasta un nodo real del grafo),
no existe ningún nodo `:Evento` cargado (`grafo/README.md` solo tiene
`:Lugar`/`:EstacionMedida`/`:ParadaTransporte`) — y Gold de `agenda_eventos`
(`agenda_eventos_por_categoria_distrito_fecha`) agrega por categoría/
distrito/fecha, **sin lat/lon por evento individual**, así que tampoco sirve
para "eventos cerca de un punto". `agenda_recintos_madrid` (la otra fuente
que el docstring original de la tool mencionaba) solo tiene captura de
muestra a Bronze, sin ningún pipeline Silver/Gold construido — queda fuera
de esta tarea.

## Qué se hizo

- **Primer caso de una `tool` de `asistente/` que lee Silver, no Gold**:
  Silver de `agenda_eventos` sí conserva lat/lon reales por evento
  (`ingesta.capturas.agenda_eventos_madrid`, ya validado por la puerta de
  calidad de `procesamiento/silver_gold/agenda_eventos/transform.py`).
  Documentado explícitamente como excepción deliberada al patrón "todo pasa
  por Gold" del resto de `tools`.
- `asistente/neo4j_client.py::resolver_lugar_query`: nueva consulta que
  resuelve `:Lugar` por texto (mismo criterio que el resto) devolviendo solo
  sus coordenadas -- sin seguir `PROXIMO_A` (no hay nada que seguir).
- `asistente/mcp_agent/tools.py::_eventos_cercanos_impl`: resuelve el lugar
  vía Neo4j, consulta Silver para una ventana de 30 días desde `momento`, y
  filtra por distancia real (`_haversine_m`, réplica local de
  `grafo/geo.py::haversine_m` -- `asistente/` se mantiene autocontenido, sin
  importar `grafo/`). Varios `:Lugar` coincidentes: se toma la distancia
  mínima a cualquiera, no a todos.
- `asistente/routers/eventos_cercanos.py`: nuevo, `GET /eventos-cercanos`.
  Caso distinto al resto de routers: `eventos_cercanos` devuelve
  `list[EventoCercano]`, no un único modelo con `fuente_dataset` -- el
  router construye la `RespuestaAsistente` a partir de la lista
  directamente.
- 9 tests nuevos en `test_mcp_tools.py` (mockeando Neo4j/Athena) + 2 en
  `test_eventos_cercanos_router.py`.

## Dos bugs reales encontrados verificando contra AWS/Neo4j real

Ninguno de los dos era visible con `FakeNeo4jDriver`/`FakeAthenaClient` --
solo aparecieron al arrancar el servicio real contra Neo4j/Athena reales:

1. **`COLUMN_NOT_FOUND: 'date'`**: la consulta a Silver usaba `date` como
   columna de partición, copiando por error la convención de Gold (que
   **renombra** `fecha` → `date` al agregar, ver
   `.withColumnRenamed("fecha", "date")` en los `glue_silver_to_gold.py` de
   varios datasets). Silver conserva su columna de partición original en
   español, `fecha` -- confirmado con `glue.get_table` real sobre
   `madrono-tfm_dev_silver.agenda_eventos`.
2. **Eventos duplicados en la respuesta** (28 filas que en realidad eran 7
   eventos distintos): Silver es un almacén persistente, no deduplicado --
   el mismo `event_id` recibe una fila nueva cada día de ingestión en que
   la fuente lo sigue listando mientras el evento sigue vigente (mismo
   comportamiento ya diagnosticado para `agenda_eventos`/`bluesky_menciones`
   en la tarea 077, pero nunca antes consumido directamente desde Silver por
   ninguna `tool` del asistente). Arreglado deduplicando por `event_id`
   antes de calcular distancias.

## Hallazgo colateral: las credenciales de Neo4j ya existen en SSM

Al preparar la verificación real se comprobó `aws ssm describe-parameters`
y aparecen `/madrono-tfm/dev/secrets/neo4j-uri`/`neo4j-username`/
`neo4j-password`/`neo4j-database` (`SecureString`, valores reales, no
placeholder) -- el gap documentado desde la tarea 043 (y que bloqueó la
mitad de la verificación de `trafico_cercano` en la tarea 081) ya no existe,
sin que ninguna tarea posterior lo documentara. No se ha repetido aquí la
verificación completa de `trafico_cercano`/`afluencia_estimada` (fuera de
alcance de esta tarea), pero `eventos_cercanos` demuestra que el driver y el
patrón de consulta genérico funcionan contra la instancia real.

## Verificación real

Arrancado el servicio real con las credenciales de SSM
(`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE`) más la
cuenta AWS del proyecto:

- `GET /eventos-cercanos?lugar=Retiro&radio_m=2000` → 7 eventos reales y
  distintos, incluidos «Esculturas desconocidas I» en «Centro de Educación
  Ambiental El Retiro» (259m) y «De hilos y sueños» en «Teatro de Títeres
  de El Retiro» (455m), `veredicto="favorable"`.
- `GET /eventos-cercanos?lugar=ZonaQueNoExisteEnMadridXYZ` →
  `fiabilidad="baja"`, `veredicto="con_precaucion"`, sin excepción.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform.
- `agenda_recintos_madrid` explícitamente fuera de alcance (sin pipeline
  Silver/Gold construido).
- Servicio local (`uvicorn`) parado al terminar; credenciales de Neo4j
  leídas en memoria desde SSM en cada arranque, nunca escritas a disco.

## Relevante para tareas futuras

- Queda 1 sola `tool` pendiente: `opciones_movilidad` (cruza 3 datasets).
- Repetir la verificación de `trafico_cercano`/`afluencia_estimada` contra
  Neo4j real ahora que las credenciales están disponibles (punto 0 de "Qué
  falta para completarlo" en `asistente/README.md`).
- El patrón "Silver es un log persistente, no deduplicado por defecto" (ya
  conocido para `agenda_eventos`/`bluesky_menciones`, tarea 077) aplica a
  cualquier `tool` futura que consulte Silver directamente en vez de Gold --
  deduplicar por clave natural antes de usar los datos, no asumir que
  "una fila = un evento real".
