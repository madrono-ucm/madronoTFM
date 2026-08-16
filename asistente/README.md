# `asistente/` — Esqueleto del asistente conversacional «Madroño» (tarea 044)

Servicio FastAPI + agente MCP que expondría el asistente conversacional
descrito en la memoria del TFM (apartados 5.2 y 6.7): responde preguntas de
movilidad y vida urbana de Madrid (p.ej. «¿voy al centro a las nueve de la
noche del viernes?») con un veredicto, un nivel de fiabilidad y una
explicación trazable a los datos.

**Estado: esqueleto, no funcional.** Este directorio define la estructura
del servicio, el esquema de su respuesta y la interfaz de sus herramientas
(`tools`) — ninguna `tool` lee datos reales todavía. Ver "Qué falta para
completarlo" más abajo.

## Por qué es solo un esqueleto

El asistente necesita leer de la capa **Gold** del lakehouse (datos
agregados y ya validados por la puerta de calidad, ver
`procesamiento/README.md`, doc/041) para responder con datos reales. Hoy
Gold solo existe como piloto de un único dataset (tráfico, tarea 041), sin
aplicar en AWS — no hay ninguna fuente real de la que leer para el resto de
señales que necesita el asistente (afluencia, calidad del aire, movilidad,
aparcamiento, eventos). Implementar la lógica de las `tools` antes de que
exista Gold para esas fuentes produciría código sin datos que consultar, o
forzaría a leer directamente de Bronze/Silver saltándose la puerta de
calidad — ninguna de las dos opciones tiene sentido en esta tarea.

## Estructura

```
asistente/
  main.py                 # create_app(): construye la app FastAPI (patrón factory)
  config.py                # Settings, dataclass + from_env() (mismo patrón que ingesta/)
  dependencies.py           # Dependencias de FastAPI (get_settings, cacheada)
  timeutils.py                # now_madrid(): misma zona horaria que ingesta/capturas/bronze.py
  routers/
    health.py                 # GET /health -- único endpoint funcional hoy
  models/
    respuesta.py                # RespuestaAsistente: veredicto/fiabilidad/explicación/fuentes
    herramientas.py               # Modelos de retorno de cada tool MCP
  mcp_agent/
    server.py                     # Instancia de MCPServer + registro de las 5 tools
    tools.py                       # Las 5 tools, con NotImplementedError
  tests/
    test_app.py                     # La app arranca y /health responde
    test_mcp_tools.py                 # Firma/docstring de las tools + registro en el servidor MCP
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
- **El agente MCP no está montado en la app FastAPI todavía.** Montar
  `MCPServer.streamable_http_app()` dentro de `FastAPI.mount()` requiere
  combinar explícitamente el ciclo de vida (`lifespan`) de ambas apps (el
  gestor de sesiones HTTP del SDK necesita arrancar/parar con la app
  principal) — un patrón real pero con nada que probar de verdad mientras
  las `tools` sigan sin lógica. Se deja como paso explícito de la tarea que
  implemente la primera `tool` real. Mientras tanto, el servidor MCP se
  ejecuta de forma independiente en modo `stdio`:
  `python -m asistente.mcp_agent.server`, la forma estándar en que un
  cliente MCP (p.ej. Claude Desktop) lo probaría en desarrollo.
- **Sin infraestructura Terraform nueva en esta tarea.** A diferencia de
  Kafka (tarea 042) o el grafo Neo4j (tarea 043), donde ya había una pieza
  de infraestructura real que describir aunque no se aplicara, desplegar
  este esqueleto (un único endpoint de salud y `tools` que solo levantan
  `NotImplementedError`) no tendría ningún efecto observable — se ha
  decidido escribir esa infraestructura (Lambda/ECS/EC2 para correr FastAPI,
  posiblemente detrás de API Gateway) cuando el servicio tenga al menos una
  `tool` real que sirva para algo.

## Esquema de la respuesta (`asistente/models/respuesta.py`)

`RespuestaAsistente`: `pregunta`, `veredicto` (`favorable` /
`desfavorable` / `con_precaucion`), `fiabilidad` (`alta` / `media` / `baja`
— cuánto cubren los datos disponibles la pregunta concreta, no la calidad de
cada dato individual), `explicacion` (texto libre) y `fuentes` (lista de
`FuenteConsultada`, cada una con el dataset de origen y un resumen — lo que
hace la explicación trazable).

## Las 5 `tools` del agente MCP (esqueleto)

De la memoria (apartado 6.7), mapeadas al productor de `ingesta/` del que
leerían en el futuro vía Gold:

| Tool | Fuente(s) futura(s) |
|---|---|
| `afluencia_prevista(lugar, momento=None)` | `afluencia_lugares_madrid` (tarea 012) |
| `calidad_aire(zona, momento=None)` | `calidad_aire_madrid` (tarea 006) + `cams_calidad_aire_madrid` (previsión, tarea 019) |
| `opciones_movilidad(origen, destino, momento=None)` | `trafico_madrid` + `transporte_publico_madrid` (EMT) + `bicimad` |
| `disponibilidad_aparcamiento(zona)` | `aparcamientos_madrid` (tarea 005) |
| `eventos_cercanos(lugar, radio_m=500.0, momento=None)` | `agenda_eventos_madrid` + `agenda_recintos_madrid` (tarea 017) |

Cada una levanta `NotImplementedError` con un mensaje que apunta a esta
tabla y a doc/041.

## Cómo correrlo

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r asistente/requirements.txt

# API HTTP (desde la raíz del repo, para que `asistente` sea importable)
uvicorn asistente.main:app --reload
# -> http://127.0.0.1:8000/health, http://127.0.0.1:8000/docs

# Agente MCP en modo stdio (para un cliente MCP como Claude Desktop)
python -m asistente.mcp_agent.server
```

## Tests

```bash
python3 -m unittest discover -s asistente/tests -t .
```

11 tests, todos en verde: que la app arranca y devuelve instancias
independientes, que `/health` responde 200 con el esquema esperado, que las
5 `tools` tienen firma/docstring completos y levantan `NotImplementedError`,
que las 5 quedan registradas en el `MCPServer`, y que `RespuestaAsistente` se
construye y serializa correctamente. Verificado además, fuera de la suite de
tests, arrancando el servidor real con `uvicorn` y confirmando `GET /health`
y `GET /docs` con `curl`.

## Qué falta para completarlo

1. **Gold real para el resto de fuentes** (doc/041 solo cubre tráfico) —
   bloqueante para implementar cualquier `tool` con lógica de verdad.
2. Con Gold disponible: reemplazar cada `NotImplementedError` por la lectura
   real (vía Athena/DuckDB sobre S3, o el cliente que decida esa tarea) y
   añadir tests con datos de ejemplo, mismo patrón que
   `procesamiento/tests/fixtures/`.
3. Un router HTTP real que reciba una pregunta en lenguaje natural, invoque
   las `tools` necesarias y construya un `RespuestaAsistente` — hoy no
   existe ningún endpoint más allá de `/health`.
4. Montar el agente MCP en la app FastAPI (`streamable_http_app()` +
   combinación de `lifespan`, ver la decisión documentada arriba) si se
   quiere servir MCP y HTTP desde el mismo proceso.
5. Infraestructura de despliegue (Lambda/ECS/EC2 + API Gateway) como código
   Terraform, sin aplicar hasta que haya una `tool` real que desplegar.
