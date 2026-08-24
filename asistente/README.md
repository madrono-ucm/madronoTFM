# `asistente/` — Asistente conversacional «Madroño»

Servicio FastAPI + agente MCP que expone el asistente conversacional
descrito en la memoria del TFM (apartados 5.2 y 6.7): responde preguntas de
movilidad y vida urbana de Madrid (p.ej. «¿voy al centro a las nueve de la
noche del viernes?») con un veredicto, un nivel de fiabilidad y una
explicación trazable a los datos.

**Estado (tarea 079): `calidad_aire` es real, el resto sigue pendiente.**
Este directorio define la estructura del servicio, el esquema de su
respuesta y la interfaz de sus 5 `tools`. La primera, `calidad_aire`, ya lee
datos reales de Gold vía Athena, está montada como agente MCP dentro de la
app FastAPI y expuesta también por HTTP (`GET /calidad-aire`) — verificado
con invocaciones reales contra la cuenta AWS de este proyecto (ver
"Verificación real" más abajo). Las otras 4 (`afluencia_prevista`,
`opciones_movilidad`, `disponibilidad_aparcamiento`, `eventos_cercanos`)
siguen levantando `NotImplementedError`; son tareas de seguimiento
separadas (ver "Qué falta para completarlo").

## Por qué solo `calidad_aire` en esta tarea

Con Silver/Gold en producción para todos los datasets y Athena ya verificado
como vía de lectura fiable (tareas 041-068), ya no hay ningún bloqueo
técnico para implementar `tools` reales. La tarea 079 eligió deliberadamente
implementar **una sola, de extremo a extremo**, en vez de varias a la vez:
el alcance amplio ya hizo que varias tareas de esta sesión agotaran
presupuesto cubriendo demasiado a la vez (ver p.ej. doc/055, doc/057).
`calidad_aire` se eligió por ser la más simple de las 5 (una sola fuente,
`gold.calidad_aire_por_estacion_contaminante_hora`, ya verificada en las
tareas 049/066/068) y la que menos depende de piezas todavía no listas (a
diferencia de `opciones_movilidad`, que cruza 3 datasets, o
`afluencia_prevista`, bloqueada sin `GOOGLE_MAPS_API_KEY`).

## Estructura

```
asistente/
  main.py                 # create_app(): construye la app FastAPI, monta el agente MCP
  config.py                # Settings, dataclass + from_env() (mismo patrón que ingesta/)
  dependencies.py           # Dependencias de FastAPI (get_settings, cacheada)
  timeutils.py                # now_madrid(): misma zona horaria que ingesta/capturas/bronze.py
  athena.py                     # run_athena_query(): consulta Gold real (mismo patrón que grafo/extract.py)
  routers/
    health.py                     # GET /health
    calidad_aire.py                 # GET /calidad-aire -- invoca la tool y construye RespuestaAsistente
  models/
    respuesta.py                # RespuestaAsistente: veredicto/fiabilidad/explicación/fuentes
    herramientas.py               # Modelos de retorno de cada tool MCP
  mcp_agent/
    server.py                     # Instancia de MCPServer + registro de las 5 tools
    tools.py                       # calidad_aire real; el resto con NotImplementedError
  tests/
    test_app.py                     # La app arranca y /health responde
    test_mcp_tools.py                 # calidad_aire (mockeando Athena) + firma/docstring/registro del resto
    test_calidad_aire_router.py        # GET /calidad-aire (mockeando Athena)
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

## Esquema de la respuesta (`asistente/models/respuesta.py`)

`RespuestaAsistente`: `pregunta`, `veredicto` (`favorable` /
`desfavorable` / `con_precaucion`), `fiabilidad` (`alta` / `media` / `baja`
— cuánto cubren los datos disponibles la pregunta concreta, no la calidad de
cada dato individual), `explicacion` (texto libre) y `fuentes` (lista de
`FuenteConsultada`, cada una con el dataset de origen y un resumen — lo que
hace la explicación trazable).

## Las 5 `tools` del agente MCP

De la memoria (apartado 6.7), mapeadas a su fuente real o futura vía Gold:

| Tool | Fuente(s) | Estado |
|---|---|---|
| `calidad_aire(zona, momento=None)` | `gold.calidad_aire_por_estacion_contaminante_hora` (tarea 006 + Gold, tarea 041+) | **Real (tarea 079)** |
| `afluencia_prevista(lugar, momento=None)` | `afluencia_lugares_madrid` (tarea 012) | `NotImplementedError` |
| `opciones_movilidad(origen, destino, momento=None)` | `trafico_madrid` + `transporte_publico_madrid` (EMT) + `bicimad` | `NotImplementedError` |
| `disponibilidad_aparcamiento(zona)` | `aparcamientos_madrid` (tarea 005) | `NotImplementedError` |
| `eventos_cercanos(lugar, radio_m=500.0, momento=None)` | `agenda_eventos_madrid` + `agenda_recintos_madrid` (tarea 017) | `NotImplementedError` |

Las 4 pendientes levantan `NotImplementedError` con un mensaje que apunta a
esta tabla y a doc/041; son tareas de seguimiento independientes, no
bloqueadas por esta.

`calidad_aire` resuelve `zona` por **coincidencia de texto** (case
insensitive) sobre `station_name`/`station_id` de la propia tabla Gold —
p.ej. "Ramón y Cajal", "Plaza del Carmen" (nombres reales de estaciones de
esta cuenta) — **no** contra un barrio/distrito real: Gold no tiene esa
dimensión espacial (es el trabajo del grafo, tareas 043/067-071). Si no
encuentra ninguna estación coincidente, no lanza una excepción: devuelve
`indice_calidad="sin_datos"` (ver `asistente/mcp_agent/tools.py` y
`asistente/routers/calidad_aire.py`).

## Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r asistente/requirements.txt

# API HTTP (desde la raíz del repo, para que `asistente` sea importable).
# AWS_DEFAULT_REGION=eu-west-1 es necesario en esta EC2: su región de IMDS
# por defecto (eu-south-2) no coincide con la región real de la cuenta
# (eu-west-1, ver grafo/README.md) y boto3 no la resuelve solo -- sin esta
# variable, GET /calidad-aire falla con botocore.exceptions.NoRegionError.
AWS_DEFAULT_REGION=eu-west-1 uvicorn asistente.main:app --reload
# -> http://127.0.0.1:8000/health, http://127.0.0.1:8000/docs
# -> http://127.0.0.1:8000/calidad-aire?zona=Ram%C3%B3n%20y%20Cajal

# Agente MCP en modo stdio (para un cliente MCP como Claude Desktop)
python -m asistente.mcp_agent.server
```

## Tests

```bash
python3 -m unittest discover -s asistente/tests -t .
```

20 tests, todos en verde: que la app arranca (con el agente MCP montado y su
`lifespan` combinado) y devuelve instancias independientes, que `/health`
responde 200, que `calidad_aire` calcula bien el índice/contaminante
principal en varios escenarios (una estación, varias estaciones
coincidentes, sin coincidencias, sin `momento`, contaminante sin límite de
referencia -- mockeando Athena con un `FakeAthenaClient`, sin conexión ni
credenciales reales), que las 4 `tools` restantes siguen levantando
`NotImplementedError`, que las 5 quedan registradas en el `MCPServer`, que
`GET /calidad-aire` construye la `RespuestaAsistente` esperada (con y sin
estación encontrada, mockeando Athena), y que `RespuestaAsistente` se
construye y serializa correctamente.

## Verificación real

Arrancado el servicio real (`AWS_DEFAULT_REGION=eu-west-1 uvicorn
asistente.main:app`) contra la cuenta AWS de este proyecto (`eu-west-1`,
`222234418587`), `GET /calidad-aire?zona=Ram%C3%B3n%20y%20Cajal` devolvió un
`avg_value` de NO2 real (5.0 µg/m³ a las 21:00 del día de la ejecución),
`veredicto="favorable"`, `fiabilidad="alta"`, con `fuentes` citando el
dataset y la estación. Repetido con "Plaza del Carmen" (otra estación real)
y con una zona inexistente (`fiabilidad="baja"`, sin excepción). Verificado
también que el agente MCP montado responde en `/mcp-server/mcp` (con
`TestClient` como gestor de contexto: el `lifespan` combinado arranca y para
el `StreamableHTTPSessionManager` correctamente).

## Qué falta para completarlo

1. Implementar las 4 `tools` restantes (`afluencia_prevista`,
   `opciones_movilidad`, `disponibilidad_aparcamiento`, `eventos_cercanos`),
   cada una como tarea de seguimiento separada — mismo patrón que
   `calidad_aire` (tool en `tools.py` + router HTTP + tests mockeando
   Athena).
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
