# 089 — Asistente: `afluencia_estimada` (redisenada tras el hallazgo de la tarea 087)

## Qué se implementó

`afluencia_estimada(lugar, radio_m=300.0, momento=None)`, sustituye a
`afluencia_prevista` (esqueleto original, tarea 044, bloqueada sin
`GOOGLE_MAPS_API_KEY`). Mismo patrón que `trafico_cercano` (tarea 081),
repetido cuatro veces: resuelve `lugar` contra `:Lugar` en el grafo y sigue
`PROXIMO_A` hasta cada tipo de nodo dentro de `radio_m`, cruzando con su
tabla Gold correspondiente.

- **`asistente/neo4j_client.py`**: tres consultas nuevas
  (`lugares_proximos_a_estaciones_ruido_query`, `..._calidad_aire_query`,
  `lugares_proximos_a_paradas_bicimad_query`), calcadas de
  `lugares_proximos_a_estaciones_trafico_query` -- no se factorizó una
  función genérica compartida: el proyecto ya prefiere varias funciones de
  consulta pequeñas y explícitas antes que una abstracción (mismo criterio
  que `grafo/nodos.py::estacion_medida_from_*_gold`), y un primer intento
  de factorizar rompía los tests existentes de `trafico_cercano` sin
  aportar nada a cambio.
- **`asistente/models/herramientas.py`**: `AfluenciaPrevista` (nunca
  construida) sustituida por `AfluenciaEstimada` + tres modelos nuevos de
  estación cercana (`EstacionRuidoCercana`, `ParadaBicimadCercana`,
  `EstacionCalidadAireCercana`).
- **`asistente/mcp_agent/tools.py::afluencia_estimada`**: combina cuatro
  señales. Tráfico, ruido y BiciMAD alimentan `nivel_estimado`
  (`"bajo"`/`"medio"`/`"alto"`/`"sin_datos"`, etiqueta simplificada);
  calidad del aire se lista solo para trazabilidad, deliberadamente
  excluida del cálculo (señal más débil/indirecta).
- **`asistente/routers/afluencia_estimada.py`** + registro en
  `asistente/main.py` (`GET /afluencia-estimada`) y
  `asistente/mcp_agent/server.py`.

## Por qué esta forma, y no la del diseño original (tarea 086)

La especificación original (tarea 086) elegía `aforos_peatones_bicicletas`
como señal primaria. La tarea 087 verificó contra Athena/S3 reales que esa
fuente municipal está descontinuada desde el 30/6/2024 (confirmado también
de forma independiente contra `datos.madrid.es`) -- no hay ningún dato en
vivo que ofrecer desde ahí. Decisión tomada con el usuario: combinar
tráfico + ruido + BiciMAD + calidad del aire en su lugar, las cuatro con
datos reales y frescos verificados en la misma sesión (ver
`grafo/README.md`, "Verificado contra datos reales").

Ninguna de las cuatro señales mide peatones directamente -- es una
aproximación por actividad urbana general, documentada así explícitamente
en el docstring de `AfluenciaEstimada` y en la respuesta HTTP, no un
conteo de personas.

## Bug real encontrado en `grafo/README.md`/tests, no de esta tool

Ninguno -- las cuatro consultas Gold usadas aquí ya estaban verificadas
contra datos reales por trabajo anterior (tráfico, tarea 041; ruido,
calidad del aire, BiciMAD, tarea 069/087). La única pieza nueva
(BiciMAD/ruido/calidad_aire vía grafo) se verificó de extremo a extremo en
esta misma tarea -- ver siguiente sección.

## Verificación real de extremo a extremo

Ejecutada contra la instancia real de Neo4j AuraDB Free (credenciales de
SSM, `eu-west-1`) y Athena reales, desde un entorno de desarrollo local con
las credenciales AWS ya configuradas (ver `doc/087-...md`, "Corrección
25/8" -- mismo hallazgo de que sí había credenciales reales disponibles).

`afluencia_estimada("Plaza de España", 300.0, momento=None)` (instante
actual, 25/8/2026): el cruce por grafo funcionó perfectamente -- 23
estaciones de tráfico, 1 de ruido, 3 paradas BiciMAD y 1 estación de
calidad del aire encontradas dentro de 300m, todas reales. Gold no tenía
fila para la fecha/hora exactas de la invocación (`nivel_estimado:
"sin_datos"`, valores `None`) -- comportamiento correcto, no un bug (mismo
caso ya documentado en `trafico_cercano`/tarea 082: el grafo encuentra
nodos reales sin que Gold tenga necesariamente una fila para ese instante
exacto).

Repetido con un `momento` reciente explícito
(`2026-08-25T10:00:00+02:00`): las cuatro señales devolvieron datos reales
combinados:

```
nivel_estimado: bajo
hora: 10
trafico: 23 nodos -- ejemplo: point_id=4286, distancia_m=35.6,
  avg_intensity_vph=985.1, avg_occupancy_ratio=0.099, avg_service_level=1.0
bicimad: 3 nodos -- ejemplo: station_id=2406, distancia_m=13.1,
  avg_bikes_available=0.0, avg_docks_available=12.0, avg_occupancy_ratio=0.0
ruido: 1 nodo -- ejemplo: station_id=RF-04, distancia_m=69.0,
  avg_laeq_db=None (sin fila Gold esa fecha para esa estación -- caso real
  de "grafo encuentra, Gold no tiene dato", manejado correctamente)
calidad_aire: 1 nodo -- ejemplo: station_id=28079004, distancia_m=55.5,
  contaminante_principal=PM10, valor=17.0
```

## Tests

`asistente/tests/` completo, 39 tests en verde:

- `test_afluencia_estimada.py` (5 tests, mocks con routing por
  `tipo`/tabla -- necesario porque esta tool hace hasta 4 llamadas a
  Neo4j/Athena, a diferencia de `calidad_aire`/`trafico_cercano` que hacen
  una sola): sin ningún nodo cercano, solo una señal disponible, las tres
  señales combinadas en `nivel_estimado`, calidad del aire no contribuye al
  cálculo, nodo cercano sin fila Gold se lista con valores `None`.
- `test_afluencia_estimada_router.py` (2 tests): `GET /afluencia-estimada`
  sin datos y con señal de tráfico.
- `test_mcp_tools.py`/`test_app.py`: actualizados (`afluencia_prevista` ->
  `afluencia_estimada` en las listas de tools/registro).

## Restricciones respetadas

- No se ha tocado `calidad_aire` ni `trafico_cercano`.
- No se ha usado `aforos_peatones_bicicletas` como señal (código de la
  tarea 087 se deja intacto, sin usar).
- No se ha implementado `agenda_eventos`/`agenda_recintos` como señal.
- No se ha reactivado `ingesta/capturas/afluencia_lugares_madrid.py`/
  `populartimes`.
- No se ha modificado `grafo/`.

## Relevante para tareas futuras

- El bloqueador de la clave de Google Maps queda completamente cerrado:
  ninguna `tool` del asistente depende ya de `GOOGLE_MAPS_API_KEY`.
- `ruido_por_estacion_periodo_fecha` no tiene columna `hour` (solo `date` +
  `period`) -- `afluencia_estimada` toma cualquier fila del día sin filtrar
  por periodo, una simplificación deliberada documentada en el código; una
  futura mejora podría elegir el `period` (D/N/T) más cercano a la hora
  consultada.
- Persistir `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros
  SSM `SecureString` sigue pendiente (gap documentado desde la tarea 043,
  `NEXT_STEPS.md` Prioridad 4) -- esta verificación los leyó a mano desde
  SSM en un script puntual, no desde el propio servicio.
