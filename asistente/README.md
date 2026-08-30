# `asistente/` — Asistente conversacional «Madroño»

Servicio FastAPI + agente MCP que expone el asistente conversacional
descrito en la memoria del TFM (apartados 5.2 y 6.7): responde preguntas de
movilidad y vida urbana de Madrid (p.ej. «¿voy al centro a las nueve de la
noche del viernes?») con un veredicto, un nivel de fiabilidad y una
explicación trazable a los datos.

**Estado (tarea `ML_09`): 7 `tools`, todas con lógica real.** Este
directorio define la estructura del servicio, el esquema de su respuesta y
la interfaz de 7 `tools` (las 5 originales del esqueleto de la tarea 044,
más `trafico_cercano`, tarea 081, y `calidad_aire_prevista`, tarea `ML_09`).
`calidad_aire`
(tarea 079) y `disponibilidad_aparcamiento` (tarea 090) leen datos reales de
Gold vía Athena directamente (una sola tabla cada una, sin grafo).
`trafico_cercano` (tarea 081) y `afluencia_estimada` (tarea 089) son las
`tools` que **cruzan datasets vía el grafo urbano en Neo4j** (tarea 080):
resuelven un lugar contra el grafo, siguen la relación `PROXIMO_A` hasta los
nodos cercanos, y consultan Gold para su estado. `afluencia_estimada`
sustituye a la `afluencia_prevista` original (bloqueada sin
`GOOGLE_MAPS_API_KEY`) -- combina tráfico, ruido, BiciMAD y calidad del aire
en vez de `aforos_peatones_bicicletas` (la señal originalmente elegida,
tarea 086, verificada como fuente municipal descontinuada desde 2024-06-30,
ver `doc/087-...md`). `disponibilidad_aparcamiento` estaba bloqueada hasta
que la tarea 090 verificó que Gold de `aparcamientos` ya tenía datos reales
(el bug de `doc/052` había quedado resuelto como efecto colateral de las
tareas 072/075, sin que nadie lo hubiera comprobado -- ver `doc/090-...md`).
`eventos_cercanos` (tarea 095) resuelve el lugar contra el grafo (sin seguir
ninguna relación -- no hay ningún nodo `:Evento`) y filtra por distancia
real (Haversine) contra **Silver** de `agenda_eventos`, no Gold (que agrega
por categoría/distrito/fecha sin lat/lon por evento, ver `doc/095-...md`) --
primer caso de una `tool` que lee Silver en vez de Gold. `opciones_movilidad`
(tarea 096) es la última y la única con una **simplificación deliberada
real**: no calcula ninguna ruta ni duración de viaje (no existe ningún grafo
de calles transitable -- `CONECTADO_CON`, tarea 071, solo conecta paradas de
transporte público a lo largo de una línea CRTM, no un callejero) -- en su
lugar resuelve origen/destino por separado contra el grafo y describe las
condiciones reales de tráfico/BiciMAD/EMT cerca de cada extremo, sin
inventar una duración. `calidad_aire_prevista` (tarea `ML_09`) cierra el
bucle observación→predicción→asistente de la memoria (§6.7 / §4.1): sirve
una **previsión** de calidad del aire a 1/3/6 h corriendo el modelo **ONNX**
de `ML_07` (LightGBM multi-horizonte de `ML_03`, exportado; copia vendida en
`asistente/modelos/`) sobre las 19 features de `modelado/export/CONTRATO.md`,
construidas a partir de las últimas 24 h de Gold. Ancla el forecast en la
última hora con lectura real (Gold va con retraso) y baja la fiabilidad si
faltan features históricas. Las siete están montadas como agente MCP dentro
de la app FastAPI y expuestas también por HTTP (`GET /calidad-aire`,
`GET /calidad-aire-prevista`, `GET /trafico-cercano`,
`GET /afluencia-estimada`, `GET /disponibilidad-aparcamiento`,
`GET /eventos-cercanos`, `GET /opciones-movilidad`) — verificado con
invocaciones reales contra la cuenta AWS de este proyecto, incluida la
instancia real de Neo4j (ver "Verificación real" más abajo). No queda
ninguna `tool` con `NotImplementedError`.

## Por qué solo `calidad_aire` en esta tarea

Con Silver/Gold en producción para todos los datasets y Athena ya verificado
como vía de lectura fiable (tareas 041-068), ya no hay ningún bloqueo
técnico para implementar `tools` reales. La tarea 079 eligió deliberadamente
implementar **una sola, de extremo a extremo**, en vez de varias a la vez:
el alcance amplio ya hizo que varias tareas de esta sesión agotaran
presupuesto cubriendo demasiado a la vez (ver p.ej. doc/055, doc/057).
`calidad_aire` se eligió por ser la más simple de las 5 originales (una sola
fuente, `gold.calidad_aire_por_estacion_contaminante_hora`, ya verificada en
las tareas 049/066/068) y la que menos depende de piezas todavía no listas
(a diferencia de `opciones_movilidad`, que cruza 3 datasets).

## Estructura

```
asistente/
  main.py                 # create_app(): construye la app FastAPI, monta el agente MCP
  config.py                # Settings, dataclass + from_env() (mismo patrón que ingesta/)
  dependencies.py           # Dependencias de FastAPI (get_settings, cacheada)
  timeutils.py                # now_madrid(): misma zona horaria que ingesta/capturas/bronze.py
  athena.py                     # run_athena_query(): consulta Gold/Silver real (mismo patrón que grafo/extract.py)
  neo4j_client.py                 # run_neo4j_query() + query builders de trafico_cercano (081)/afluencia_estimada (089)/eventos_cercanos (095)/opciones_movilidad (096)
  routers/
    health.py                     # GET /health
    calidad_aire.py                 # GET /calidad-aire -- invoca la tool y construye RespuestaAsistente
    trafico_cercano.py                # GET /trafico-cercano -- ídem, tarea 081
    afluencia_estimada.py               # GET /afluencia-estimada -- ídem, tarea 089
    disponibilidad_aparcamiento.py        # GET /disponibilidad-aparcamiento -- ídem, tarea 090
    eventos_cercanos.py                     # GET /eventos-cercanos -- ídem, tarea 095 (EventosCercanos: contenedor de lista, FIL_24)
    opciones_movilidad.py                     # GET /opciones-movilidad -- ídem, tarea 096 (OpcionesMovilidad: contenedor de lista, FIL_24)
  models/
    respuesta.py                # RespuestaAsistente: veredicto/fiabilidad/explicación/fuentes
    herramientas.py               # Modelos de retorno de cada tool MCP
  mcp_agent/
    server.py                     # Instancia de MCPServer + registro de las 6 tools
    tools.py                       # las 6 tools, todas con lógica real (opciones_movilidad, tarea 096, es la última)
  tests/
    test_app.py                     # La app arranca y /health responde
    test_mcp_tools.py                 # calidad_aire/trafico_cercano/disponibilidad_aparcamiento/eventos_cercanos (mockeando Athena/Neo4j) + firma/docstring/registro del resto
    test_calidad_aire_router.py        # GET /calidad-aire (mockeando Athena)
    test_trafico_cercano_router.py       # GET /trafico-cercano (mockeando Athena y Neo4j), tarea 081
    test_afluencia_estimada.py             # _afluencia_estimada_impl (mockeando Athena/Neo4j con routing), tarea 089
    test_afluencia_estimada_router.py        # GET /afluencia-estimada, tarea 089
    test_disponibilidad_aparcamiento_router.py # GET /disponibilidad-aparcamiento (mockeando Athena), tarea 090
    test_eventos_cercanos_router.py              # GET /eventos-cercanos (mockeando Athena y Neo4j), tarea 095
    test_opciones_movilidad.py                     # _opciones_movilidad_impl (mockeando Athena/Neo4j con routing por lugar+tipo), tarea 096
    test_opciones_movilidad_router.py                # GET /opciones-movilidad, tarea 096
    test_neo4j_client.py                   # Query builders (por inspección) + run_neo4j_query
    test_respuesta.py                  # El modelo de respuesta se construye y serializa
  requirements.txt
```

Precedente directo de esta estructura: `ingesta/capturas/` + `ingesta/tests/`
(paquete de lógica + paquete hermano de tests, config como
dataclass/`from_env()`) y `procesamiento/silver_gold/<dataset>/` (un
subpaquete por área, `README.md` propio). `routers/`/`dependencies.py` es el
patrón estándar recomendado por la propia documentación de FastAPI para
proyectos con más de un endpoint — con un único router hoy (`health`) puede
parecer prematuro, pero es la estructura que evita reorganizar todo el
servicio en cuanto se añada el primer router real (respuestas del
asistente).

## Decisiones de esta tarea

- **`create_app()` como *application factory*** (`asistente/main.py`), no una
  única instancia `FastAPI()` a nivel de módulo sin función que la
  construya: permite que los tests creen instancias frescas e
  independientes (`asistente/tests/test_app.py`), patrón recomendado por la
  documentación oficial de FastAPI para testing.
- **SDK MCP**: el paquete oficial `mcp`
  (https://github.com/modelcontextprocol/python-sdk), investigado y
  verificado en esta tarea instalándolo realmente (versión resuelta: 2.0.0).
  En esa versión la clase de alto nivel para construir un servidor es
  `MCPServer` (`mcp.server.mcpserver.server`), no `FastMCP`
  (`mcp.server.fastmcp`, nombre usado en versiones anteriores del SDK y ya
  no presente en el paquete instalado) — ver el docstring de
  `asistente/mcp_agent/server.py` para el detalle completo.
- **Las `tools` son funciones planas** en `mcp_agent/tools.py`, registradas
  sobre la instancia de `MCPServer` en `mcp_agent/server.py` vía
  `MCPServer.add_tool()`, en vez de decoradas con `@mcp.tool()` directamente:
  así `tools.py` se puede importar, inspeccionar y testear
  (`test_mcp_tools.py`) sin depender de que la librería `mcp` esté instalada
  ni de que la instancia del servidor exista.
- **(Tarea 079) El agente MCP ya está montado en la app FastAPI**
  (`asistente/main.py::create_app`, `MCPServer.streamable_http_app()` +
  `FastAPI.mount("/mcp-server", mcp_app)`). `FastAPI.mount()` por sí solo no
  propaga el `lifespan` de una sub-app montada (solo Uvicorn invoca el de la
  app raíz) -- el `lifespan` de `MCPServer.streamable_http_app()` es el que
  arranca/para el `StreamableHTTPSessionManager` que gestiona las sesiones
  MCP (`lifespan=lambda app: session_manager.run()`, ver
  `mcp.server.lowlevel.server.Server.streamable_http_app`). Se combinan
  explícitamente con `contextlib.AsyncExitStack` en el `lifespan` de la app
  principal (patrón documentado por el propio SDK de MCP para este caso:
  montar `streamable_http_app()` bajo otro framework ASGI) -- ver el
  docstring de `main.py`. Verificado con `TestClient` como gestor de
  contexto (`with TestClient(app) as client:`): el log confirma
  `"StreamableHTTP session manager started"` al entrar y `"...shutting
  down"` al salir. El servidor MCP sigue siendo también ejecutable de forma
  independiente en modo `stdio`: `python -m asistente.mcp_agent.server`.
- **(Tarea 079) `asistente/athena.py` replica el patrón de
  `grafo/extract.py::run_athena_query`** (tarea 069: `boto3` +
  `start_query_execution`/`get_query_execution`/`get_query_results`, mismo
  backoff de sondeo) en vez de importarlo directamente de `grafo/` -- mismo
  criterio ya aplicado en `timeutils.py` respecto a `ingesta/`: mantener
  `asistente/` autocontenido y desplegable de forma independiente del resto
  del monorepo.
- **`indice_calidad` es una etiqueta simplificada, no el Índice de Calidad
  del Aire oficial.** Cuando varias estaciones coinciden con `zona`
  (coincidencia de texto sobre `station_name`/`station_id`, ver la tabla de
  abajo), `calidad_aire` agrega contaminante a contaminante tomando la
  estación con mayor `avg_value` (criterio conservador: el peor caso entre
  las que coinciden), y elige `contaminante_principal` por su ratio frente a
  un límite/umbral de referencia oficial (Real Decreto 102/2011 / Directiva
  2008/50/CE) -- NO2/SO2/O3 usan su límite/umbral horario oficial;
  PM10/PM2.5/CO no tienen límite horario oficial, así que se usa su límite
  diario/anual/8h como referencia aproximada. Documentado como aproximación
  deliberada en `asistente/mcp_agent/tools.py` (mismo criterio que la tarea
  078 con el precio de Glue: número simple, con su limitación documentada,
  en vez de no dar ningún número). Si el contaminante presente no tiene
  límite de referencia conocido (p.ej. NOx, tolueno), se usa como último
  recurso el de mayor `avg_value` bruto y `indice_calidad="sin_clasificar"`.
- **Sin infraestructura Terraform nueva en esta tarea.** Igual que decidió
  la tarea 044: se pospone la infraestructura de despliegue (Lambda/ECS/EC2
  + API Gateway) hasta que el enunciado de una tarea la pida explícitamente
  -- el criterio de "esperar a tener una `tool` real" ya se cumple desde
  esta tarea, pero desplegar sigue siendo una decisión aparte de implementar.
- **(Tarea 081) `asistente/neo4j_client.py` es un cliente de solo lectura,
  independiente de `grafo/cypher.py`.** `grafo/cypher.py` solo tiene métodos
  de *escritura* (`Neo4jLoader.load_*`, pensados para `cargar_grafo.py`) --
  no se amplió ni se reutilizó, siguiendo la restricción explícita de la
  tarea de no tocar `grafo/`. `run_neo4j_query()` replica la forma de
  `asistente/athena.py::run_athena_query()` (función con cliente/driver
  inyectable, en vez de una clase con gestor de contexto como
  `Neo4jLoader`): aquí solo hace falta una consulta puntual por invocación
  de la tool, no una sesión de carga masiva con múltiples `load_*`.
- **(Tarea 081) `trafico_cercano` usa un patrón Cypher no dirigido**
  (`(l:Lugar)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'trafico'})`, sin
  flecha): la relación `PROXIMO_A` se carga en un único sentido por pareja
  de nodos (ver `grafo/relaciones.py::proximo_a`), y su propio docstring
  documenta que "una consulta que necesite ambos sentidos usa un patrón no
  dirigido" -- exactamente este caso, ya que el sentido real depende del
  orden en que `cargar_grafo.py` cargó cada tipo de nodo (detalle de
  implementación, no del esquema).
- **(Tarea 081) `resumen` (`"fluido"`/`"denso"`/`"congestionado"`) se basa en
  `avg_service_level`** (el campo real "nivelServicio" de la API de tráfico
  de Madrid, escala 0-6, ver `ingesta/capturas/trafico_madrid.py`), con
  `avg_occupancy_ratio` como respaldo si ninguna estación encontrada trae
  `avg_service_level` -- mismo criterio que `calidad_aire`: una etiqueta
  simplificada con su aproximación documentada, no una métrica oficial.

## Esquema de la respuesta (`asistente/models/respuesta.py`)

`RespuestaAsistente`: `pregunta`, `veredicto` (`favorable` /
`desfavorable` / `con_precaucion`), `fiabilidad` (`alta` / `media` / `baja`
— cuánto cubren los datos disponibles la pregunta concreta, no la calidad de
cada dato individual), `explicacion` (texto libre) y `fuentes` (lista de
`FuenteConsultada`, cada una con el dataset de origen y un resumen — lo que
hace la explicación trazable).

### Envoltorio de las tools de previsión — `RespuestaPrevision` (`FIL_15`)

Toda tool `*_prevista` (`calidad_aire_prevista` de `ML_09`, `trafico_prevista`
de `FIL_13`, `afluencia_prevista` de `FIL_14` — derivada: `trafico_prevista`
+ persistencia — y `calidad_aire_prevista_grafo` de `FIL_26` — servida por el
STGNN de grafo de `ML_05`) devuelve una **subclase** de `RespuestaPrevision`,
con el mismo contrato de procedencia y de degradación:

| Campo | Significado |
|---|---|
| `disponible` | ¿Se pudo producir una cifra? `True` ⇔ `valor_previsto is not None` |
| `horizonte_horas` | Horas por delante (1, 3 o 6) |
| `momento` | Instante de **anclaje**: última hora con lectura real en Gold (Gold va con retraso) |
| `momento_objetivo` | Hora de pared a la que aplica la previsión (`momento + horizonte_horas`); `None` si no hubo anclaje |
| `valor_previsto` / `valor_actual` / `unidad` | Cifra prevista, última lectura real y unidad (µg/m³ / `avg_service_level`) |
| `nivel_previsto` | Etiqueta simplificada del dominio (`buena`… / `fluido`… / `sin_datos`) |
| `motivo` | Por qué no hay cifra (solo si `not disponible`) — texto legible |
| `modelo` | `<target>_h<H>.onnx` + nombre del modelo del registry (`version_modelo`) |
| `data_completeness` | Fracción de {actual, lag 1/2/3/24 h} presente (0..1); proxy de confianza |
| `ventana_datos` | Rango de fechas de los lags usados (`YYYY-MM-DD..YYYY-MM-DD`) |
| `fuente_dataset` | Tabla Gold de origen |
| `generado_en` | Momento en que se construyó **esta respuesta** (≠ `momento`) |

`CalidadAirePrevista` añade `zona` / `estacion` / `contaminante`;
`TraficoPrevista` añade `lugar` / `punto_id` / `fuente_grafo`;
`AfluenciaPrevista` añade `lugar` / `radio_m` / `nivel_actual` /
`senales_usadas` / `detalle_trafico_previsto` (y `valor_previsto` es la
severidad combinada `0..2`, no una unidad física);
`CalidadAirePrevistaGrafo` (`FIL_26`, la sirve el STGNN de `ML_05` vía ONNX)
añade `nodo` (`"<station_id>__<contaminante>"`) / `n_nodos_grafo` / `grafo` /
**`vecinos_influyentes`** — las conexiones del grafo que más pesan en la
predicción de ese nodo (`∂pérdida/∂edge_weight`). Nota §7.4: este STGNN
pierde a `calidad_aire_prevista` en métricas puntuales a 1 h; se sirve por la
explicabilidad de grafo, con `fiabilidad` topada en BAJA.

**Degradación elegante:** ninguna ruta lanza excepción hacia el cliente MCP.
Si falta el `.onnx`, si Gold no tiene lags para `momento`, o si Athena/Neo4j
fallan, la tool devuelve el objeto con `disponible=False`,
`valor_previsto=None` y `motivo` explicativo (cubierto por
`asistente/tests/test_mcp_hardening.py` y `test_mcp_transport.py`).

## Las 10 `tools` del agente MCP

De la memoria (apartado 6.7). **Todas tienen lógica real** — ninguna
`NotImplementedError` (`FIL_29` limpió esta tabla, que databa de antes de
las tareas 090/095/096). Registro y anotaciones: `asistente/mcp_agent/server.py`.

| Tool | Fuente(s) | Introducida en |
|---|---|---|
| `calidad_aire(zona, momento=None)` | `gold.calidad_aire_por_estacion_contaminante_hora` vía Athena | tarea 079 |
| `trafico_cercano(lugar, radio_m=300.0, momento=None)` | grafo Neo4j (`:Lugar`-`PROXIMO_A`-`:EstacionMedida`) + `gold.trafico_por_punto_hora` | tarea 081 |
| `afluencia_estimada(lugar, radio_m=300.0, momento=None)` | grafo Neo4j + Gold de tráfico/ruido/BiciMAD/calidad_aire | tarea 089 |
| `disponibilidad_aparcamiento(zona, momento=None)` | `gold.aparcamientos_por_parking_hora` vía Athena | tarea 090 |
| `eventos_cercanos(lugar, radio_m=500.0, momento=None)` | grafo Neo4j (coords de `:Lugar`) + `silver.agenda_eventos` | tarea 095 |
| `opciones_movilidad(origen, destino, momento=None)` | grafo Neo4j + Gold de tráfico/BiciMAD/EMT (sin *routing* real, ver su docstring) | tarea 096 |
| `calidad_aire_prevista(zona, horizonte_horas=6, momento=None)` | previsión ONNX (LightGBM `ML_07`) sobre 19 features de Gold | `ML_09` |
| `trafico_prevista(lugar, horizonte_horas=6, radio_m=300.0, momento=None)` | ídem sobre `avg_service_level` del punto de tráfico resuelto por el grafo | `FIL_13` |
| `afluencia_prevista(lugar, horizonte_horas=6, radio_m=300.0, momento=None)` | **derivada**: `trafico_prevista` + persistencia de ruido/BiciMAD | `FIL_14` |
| `calidad_aire_prevista_grafo(zona, horizonte_horas=3, momento=None)` | **STGNN de grafo** (`ML_05`) vía ONNX + importancia de aristas | `FIL_26` |

Ninguna lanza excepción por falta de datos: devuelven un objeto con
`indice_calidad`/`resumen`/`nivel_*` = `"sin_datos"` (o, en las `*_prevista`,
`disponible=false` + `motivo`).

`calidad_aire` resuelve `zona` por **coincidencia de texto** (case
insensitive) sobre `station_name`/`station_id` de la propia tabla Gold —
p.ej. "Ramón y Cajal", "Plaza del Carmen" (nombres reales de estaciones de
esta cuenta) — **no** contra un barrio/distrito real: Gold no tiene esa
dimensión espacial (es el trabajo del grafo, tareas 043/067-071). Si no
encuentra ninguna estación coincidente, no lanza una excepción: devuelve
`indice_calidad="sin_datos"` (ver `asistente/mcp_agent/tools.py` y
`asistente/routers/calidad_aire.py`).

`trafico_cercano` (tarea 081) resuelve `lugar` igual (coincidencia de texto
sobre el nombre del nodo `:Lugar` del grafo), sigue la relación `PROXIMO_A`
(umbral de carga 300m, tarea 070) hasta las `EstacionMedida` de tipo
`"trafico"` a menos de `radio_m`, y consulta `gold.trafico_por_punto_hora`
para su estado más reciente. Si no hay ningún `:Lugar` coincidente, o
ninguna estación de tráfico dentro del radio, devuelve
`resumen="sin_datos"` sin lanzar ninguna excepción (ver
`asistente/mcp_agent/tools.py` y `asistente/routers/trafico_cercano.py`).

## Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r asistente/requirements.txt

# API HTTP (desde la raíz del repo, para que `asistente` sea importable).
# AWS_DEFAULT_REGION=eu-west-1 es necesario en esta EC2: su región de IMDS
# por defecto (eu-south-2) no coincide con la región real de la cuenta
# (eu-west-1, ver grafo/README.md) y boto3 no la resuelve solo -- sin esta
# variable, GET /calidad-aire falla con botocore.exceptions.NoRegionError.
#
# NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD (NEO4J_DATABASE, opcional) son
# necesarias para GET /trafico-cercano -- mismas variables que
# grafo/cargar_grafo.py, ver infra/neo4j/README.md. Sin ellas, la primera
# petición a /trafico-cercano falla con KeyError al construir el driver
# (asistente/neo4j_client.py::_driver_from_env), no antes (import perezoso).
AWS_DEFAULT_REGION=eu-west-1 NEO4J_URI=neo4j+s://... NEO4J_USERNAME=neo4j \
  NEO4J_PASSWORD=... uvicorn asistente.main:app --reload
# -> http://127.0.0.1:8000/health, http://127.0.0.1:8000/docs
# -> http://127.0.0.1:8000/calidad-aire?zona=Ram%C3%B3n%20y%20Cajal
# -> http://127.0.0.1:8000/trafico-cercano?lugar=Retiro

# Agente MCP en modo stdio (para un cliente MCP como Claude Desktop)
python -m asistente.mcp_agent.server
```

### Conectar un cliente MCP (`stdio`) — `FIL_15`

El servidor se ejecuta en `stdio` (`python -m asistente.mcp_agent.server`,
`serverInfo.name = "madrono"`) o montado en HTTP bajo `/mcp-server`
(`uvicorn asistente.main:app`, transporte *streamable HTTP*). Configuración
de ejemplo para Claude Desktop (`claude_desktop_config.json`) u otro cliente
MCP que hable `stdio`:

```json
{
  "mcpServers": {
    "madrono": {
      "command": "python",
      "args": ["-m", "asistente.mcp_agent.server"],
      "cwd": "/ruta/al/repo/madrono",
      "env": {
        "AWS_DEFAULT_REGION": "eu-west-1",
        "NEO4J_URI": "neo4j+s://xxxx.databases.neo4j.io",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "..."
      }
    }
  }
}
```

`AWS_*` habilita las tools que leen Gold vía Athena; `NEO4J_*` las que
cruzan el grafo. Sin credenciales el `initialize` + `list_tools` siguen
funcionando (descubrimiento), y cada `call_tool` degrada con `motivo` en vez
de fallar. El handshake real por `stdio` y el round-trip de `list_tools` /
`call_tool` están verificados en
`asistente/tests/test_mcp_transport.py`.

**Metadatos que ve el cliente** (`asistente/mcp_agent/server.py`):

- `initialize` devuelve `instructions` — cómo resolver «lugar»/«zona» (por
  texto, no por coordenadas), que `sin_datos`/`disponible=false` no es un
  error, que las `*_prevista` son demostración de metodología con ventana
  corta, y que la ingesta está congelada (datos hasta ~2026-08-29).
- Cada tool lleva `title` legible y `annotations` con
  `readOnlyHint=true` + `openWorldHint=true` (las 9 sólo leen datos vivos:
  `SELECT` en Athena / `MATCH` en Neo4j / inferencia ONNX).
- Las 9 anuncian `inputSchema` **y** `outputSchema` (`FIL_24`).

## Tests

```bash
python3 -m unittest discover -s asistente/tests -t .
```

32 tests, todos en verde: que la app arranca (con el agente MCP montado y su
`lifespan` combinado) y devuelve instancias independientes, que `/health`
responde 200, que `calidad_aire` calcula bien el índice/contaminante
principal en varios escenarios (una estación, varias estaciones
coincidentes, sin coincidencias, sin `momento`, contaminante sin límite de
referencia -- mockeando Athena con un `FakeAthenaClient`, sin conexión ni
credenciales reales), que `trafico_cercano` combina grafo y Gold en varios
escenarios (una estación, varias estaciones ordenadas por distancia, sin
lugar coincidente, estación encontrada sin dato Gold para la hora, respaldo
a `avg_occupancy_ratio` sin `avg_service_level`, sin `momento` -- mockeando
Neo4j con un `FakeNeo4jDriver` y Athena con `FakeAthenaClient`, ver
`asistente/tests/test_mcp_tools.py`), que la consulta Cypher de
`trafico_cercano` se genera correctamente por inspección (sin conexión ni el
paquete `neo4j` instalado, mismo criterio que `grafo/tests/test_cypher.py`,
ver `asistente/tests/test_neo4j_client.py`), que `disponibilidad_aparcamiento`
(tarea 090) suma plazas correctamente en varios escenarios (un aparcamiento,
varios aparcamientos coincidentes -- suma, no peor caso, a diferencia de
`calidad_aire`--, sin coincidencias, sin `momento`, `avg_free_spaces` nulo
excluido de la suma -- mockeando Athena con `FakeAthenaClient`, ver
`asistente/tests/test_mcp_tools.py::DisponibilidadAparcamientoToolTests`),
que `eventos_cercanos` (tarea 095) resuelve el lugar y filtra por distancia
Haversine en varios escenarios (evento dentro/fuera de radio, sin
coordenadas, varios `:Lugar` coincidentes -- distancia mínima a cualquiera,
orden por distancia, ventana de 30 días, deduplicación por `event_id` --
mockeando Neo4j y Athena, ver
`asistente/tests/test_mcp_tools.py::EventosCercanosToolTests`), que
`opciones_movilidad` (tarea 096) describe condiciones de tráfico/BiciMAD/EMT
cerca de origen y destino en varios escenarios (ambos extremos con datos,
solo uno resuelve contra el grafo, ni uno ni otro, sin `momento` -- mockeando
Neo4j y Athena con `_RoutingNeo4jDriver`/`_RoutingAthenaClient`, que enrutan
por lugar/tipo/tabla, ver `asistente/tests/test_opciones_movilidad.py`), que
las 6 `tools` ya no tienen ninguna con `NotImplementedError`, que las 6
quedan registradas en el `MCPServer`, que `GET /calidad-aire`,
`GET /trafico-cercano`, `GET /disponibilidad-aparcamiento`,
`GET /eventos-cercanos` y `GET /opciones-movilidad` construyen la
`RespuestaAsistente` esperada (con y sin estación/lugar/aparcamiento/evento
encontrado, mockeando Athena/Neo4j), y que `RespuestaAsistente` se construye
y serializa correctamente.

## Verificación real

**`calidad_aire` (tarea 079)**: arrancado el servicio real
(`AWS_DEFAULT_REGION=eu-west-1 uvicorn asistente.main:app`) contra la cuenta
AWS de este proyecto (`eu-west-1`, `222234418587`),
`GET /calidad-aire?zona=Ram%C3%B3n%20y%20Cajal` devolvió un `avg_value` de
NO2 real (5.0 µg/m³ a las 21:00 del día de la ejecución),
`veredicto="favorable"`, `fiabilidad="alta"`, con `fuentes` citando el
dataset y la estación. Repetido con "Plaza del Carmen" (otra estación real)
y con una zona inexistente (`fiabilidad="baja"`, sin excepción). Verificado
también que el agente MCP montado responde en `/mcp-server/mcp` (con
`TestClient` como gestor de contexto: el `lifespan` combinado arranca y para
el `StreamableHTTPSessionManager` correctamente).

**`trafico_cercano` (tarea 081) -- verificación parcial, ver limitación
real de esta sesión**: la mitad de Athena/Gold se verificó contra datos
reales (`run_athena_query` sobre `trafico_por_punto_hora` devolvió filas
reales del día de la ejecución, p.ej. `point_id="10053"`,
`avg_intensity_vph=72.0`, `avg_service_level=0.0` a las 22:00). **La mitad
de Neo4j no se pudo verificar contra la instancia real en esta sesión**:
las credenciales `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` que usó la
tarea 080 para cargar el grafo no están accesibles desde este entorno --
comprobado explícitamente: no existe ningún parámetro `neo4j-*` en SSM
(`aws ssm describe-parameters` sobre toda la cuenta, solo aparecen
`aemet`/`cams-ads`/`emt-*`/`google-maps`) y el rol de esta EC2
(`madrono-terraform-deployerEC2`) no tiene ningún permiso
`secretsmanager:GetSecretValue` (`AccessDeniedException` explícita, no
"secreto no encontrado", probado contra varios nombres plausibles). Esto es
coherente con `infra/neo4j/README.md` (tarea 043), que documenta
explícitamente que nunca se añadió un parámetro SSM para Neo4j "porque
todavía no existe ningún proceso de carga Gold → Neo4j que lo consuma" -- la
tarea 080 debió recibir las credenciales de forma efímera (pegadas en su
conversación), sin persistirlas en ningún gestor de secretos, algo que el
enunciado de esta tarea 081 no tenía forma de saber. En su lugar, se
verificó exhaustivamente **todo lo demás**: la consulta Cypher generada por
inspección (`asistente/tests/test_neo4j_client.py`), el driver `neo4j`
instalado y funcional (`pip show neo4j` → 5.28.4), y la lógica completa de
cruce grafo+Gold con un `FakeNeo4jDriver`+`FakeAthenaClient` (6 escenarios,
`asistente/tests/test_mcp_tools.py::TraficoCercanoToolTests`). **Queda
como primer paso de una tarea de seguimiento**: repetir esta verificación
con `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` reales en el entorno
(pedirlas a quien las generó en la tarea 080, o rotarlas desde la consola de
Aura si se han perdido) contra un `:Lugar` real del grafo (`MATCH (l:Lugar)
RETURN l.nombre LIMIT 20` para elegir uno) -- y, si se quiere evitar este
mismo bloqueo en el futuro, completar el punto ya señalado en
`infra/neo4j/README.md`: añadir `NEO4J_URI`/`NEO4J_USERNAME`/
`NEO4J_PASSWORD` como parámetros SSM `SecureString`, ahora que esta tarea sí
crea un consumidor real de esas credenciales.

**`disponibilidad_aparcamiento` (tarea 090)**: arrancado el servicio real
(`AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1 uvicorn
asistente.main:app`) contra la cuenta AWS de este proyecto,
`GET /disponibilidad-aparcamiento?zona=Plaza%20de%20Oriente` devolvió
`plazas_libres=189`/`plazas_totales=212` reales (mismos valores que la
fila real de `gold.aparcamientos_por_parking_hora` verificada por separado
con Athena, ver `doc/090-...md`), `veredicto="favorable"`,
`fiabilidad="alta"`. Repetido con "Santo Domingo" (`266`/`333`, otro
aparcamiento real) y con una zona inexistente (`fiabilidad="baja"`, sin
excepción). A diferencia de `calidad_aire`, esta `tool` no depende de
Neo4j -- Gold de `aparcamientos` ya se verificó como fuente sana en la
propia tarea 090 (`doc/090-...md`), así que la verificación es completa,
sin ninguna limitación pendiente como la de `trafico_cercano` arriba.

**El bloqueo de Neo4j de `trafico_cercano` (arriba) ya no aplica**:
comprobado en la tarea 095 que `NEO4J_URI`/`NEO4J_USERNAME`/
`NEO4J_PASSWORD`/`NEO4J_DATABASE` sí existen ahora como parámetros SSM
`SecureString` (`/madrono-tfm/dev/secrets/neo4j-*`) -- el punto señalado en
`infra/neo4j/README.md` se completó en algún momento entre la tarea 081 y
esta. No se ha repetido la verificación completa de `trafico_cercano`/
`afluencia_estimada` contra Neo4j real en esta tarea (fuera de su alcance),
pero `eventos_cercanos` (justo debajo) sí se verificó de extremo a extremo
con estas credenciales, lo que confirma que el driver/consulta genérica
funciona contra la instancia real.

**`eventos_cercanos` (tarea 095)**: arrancado el servicio real con
`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` reales
(leídos de SSM) más la cuenta AWS del proyecto,
`GET /eventos-cercanos?lugar=Retiro&radio_m=2000` devolvió 7 eventos reales
y distintos (tras corregir dos bugs reales encontrados en esta misma
verificación -- ver más abajo), entre ellos «Esculturas desconocidas I» en
«Centro de Educación Ambiental El Retiro» (259m) y «De hilos y sueños» en
«Teatro de Títeres de El Retiro» (455m), `veredicto="favorable"`. Repetido
con una zona inexistente (`fiabilidad="baja"`, sin excepción).

Dos bugs reales encontrados y corregidos en esta verificación (ninguno
visible con Athena/Neo4j mockeados):

1. `AnalysisException`/`COLUMN_NOT_FOUND: 'date'` -- la consulta a Silver
   usaba `date` como columna de partición, copiando por error la
   convención de Gold (que renombra `fecha` → `date` al agregar). Silver
   conserva su columna de partición original en español, `fecha`.
2. El mismo evento aparecía repetido varias veces en la respuesta (p.ej. 28
   resultados que en realidad eran 7 eventos distintos): Silver es un
   almacén persistente, no deduplicado -- el mismo `event_id` recibe una
   fila nueva cada día de ingestión en que la fuente lo sigue listando
   mientras el evento sigue vigente (mismo comportamiento ya documentado
   para `agenda_eventos`/`bluesky_menciones` en la tarea 077, pero nunca
   antes consumido directamente desde Silver por ninguna `tool`). Arreglado
   deduplicando por `event_id` antes de calcular distancias.

**`opciones_movilidad` (tarea 096)**: arrancado el servicio real con
credenciales de Neo4j (SSM) y la cuenta AWS del proyecto,
`GET /opciones-movilidad?origen=Retiro&destino=Sol` devolvió las 3 opciones
con datos reales y distintos en cada extremo: `coche` — tráfico fluido
cerca de ambos; `bicimad` — 8.0 bicis de media cerca del origen, 15.1
anclajes libres cerca del destino; `transporte_publico` — "sin datos" en
ambos extremos, consistente con la cobertura real muy limitada de
`transporte_publico_emt` (1 solo `stop_id` real en Gold, `NEXT_STEPS.md`
Prioridad 7) documentada en el propio docstring de la `tool`. Repetido con
dos zonas inexistentes → `fiabilidad="baja"`, `fuentes=[]`, sin excepción.

## Qué falta para completarlo

0. ~~(Tarea 081) Verificar `trafico_cercano` contra la instancia real de
   Neo4j~~ **Las credenciales ya existen en SSM** (comprobado en la tarea
   095, ver "Verificación real" arriba) -- sigue pendiente repetir la
   verificación completa de `trafico_cercano`/`afluencia_estimada` con
   ellas (`eventos_cercanos` ya demostró que el driver/consulta genérica
   funciona contra la instancia real).
1. ~~Implementar la última `tool` (`opciones_movilidad`)~~ **Hecho (tarea
   096)**, con una simplificación deliberada real: sin routing por calles
   (no existe ningún grafo transitable), describe condiciones cerca de cada
   extremo en vez de calcular una ruta -- ver su docstring y "Verificación
   real" arriba. Ya no queda ninguna `tool` de las 6 originales con
   `NotImplementedError`. Si se quiere routing real en el futuro, hace
   falta primero un grafo de calles transitable (`callejero_madrid` +
   adyacencia real entre tramos, no solo `CONECTADO_CON` de líneas CRTM).
2. `calidad_aire` no usa `cams_calidad_aire_madrid` (previsión Copernicus
   CAMS, tarea 019) — solo medición real. Combinar ambas fuentes (medición
   para el pasado/presente, previsión para el futuro cercano) queda para una
   tarea de seguimiento si se quiere que `momento` en el futuro devuelva una
   previsión en vez de "sin datos".
3. Resolución real de `zona` por barrio/distrito (en vez de coincidencia de
   texto sobre el nombre de estación) — depende del grafo (tareas 067-071).
4. Un router "pregunta en lenguaje natural" que decida qué `tool(s)`
   invocar y agregue sus resultados en una única `RespuestaAsistente` — hoy
   cada `tool` real tiene su propio endpoint HTTP dedicado
   (`GET /calidad-aire`), sin ningún orquestador de lenguaje natural.
5. Infraestructura de despliegue (Lambda/ECS/EC2 + API Gateway) como código
   Terraform, sin aplicar hasta que se decida explícitamente desplegar.
