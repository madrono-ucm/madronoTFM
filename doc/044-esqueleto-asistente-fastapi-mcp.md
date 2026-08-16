# 044 — Esqueleto del asistente conversacional (FastAPI + agente MCP)

## Qué se implementó

Directorio nuevo `asistente/`, primera pieza de la cara ciudadana del
proyecto (memoria del TFM, apartados 5.2 y 6.7): el asistente conversacional
«Madroño», que respondería preguntas de movilidad y vida urbana de Madrid
con un veredicto trazable a los datos. **Alcance de esta tarea: solo el
esqueleto** (estructura de servicio, esquema de datos, interfaz de
herramientas) — sin lógica de negocio real ni conexión a ninguna fuente de
datos, tal como pedía el enunciado. Ver `asistente/README.md` para el
detalle completo de estructura, decisiones y cómo correrlo/testearlo; este
documento resume qué cambió y por qué, para el contexto acumulado del
proyecto.

## Componentes

1. **App FastAPI mínima** (`asistente/main.py`, `routers/health.py`,
   `config.py`, `dependencies.py`): patrón *application factory*
   (`create_app()`), configuración como `dataclass` + `from_env()` (mismo
   patrón que `ingesta.capturas.trafico_madrid.CaptureConfig`, sin introducir
   `pydantic-settings` como segunda forma de leer configuración en el
   proyecto). Único endpoint funcional: `GET /health`.
2. **Esqueleto de agente MCP** (`mcp_agent/server.py`, `mcp_agent/tools.py`):
   5 `tools` (`afluencia_prevista`, `calidad_aire`, `opciones_movilidad`,
   `disponibilidad_aparcamiento`, `eventos_cercanos`), cada una con firma
   tipada y docstring que documenta su fuente futura en `ingesta/capturas/`,
   levantando `NotImplementedError` porque no hay Gold real del que leer
   (doc/041 solo cubre tráfico). Registradas sobre una instancia de
   `MCPServer` (SDK oficial `mcp`, ver decisión de SDK más abajo).
3. **Esquema de la respuesta** (`models/respuesta.py`): `RespuestaAsistente`
   (Pydantic) con `veredicto` (`favorable`/`desfavorable`/`con_precaucion`),
   `fiabilidad` (`alta`/`media`/`baja`) y `explicacion` + `fuentes`
   (`FuenteConsultada`, dataset + resumen, lo que hace la explicación
   trazable) — el contrato que describe la memoria, tal como pedía el
   enunciado.
4. **Tests** (`asistente/tests/`, `unittest`, mismo framework que
   `ingesta/tests` y `procesamiento/tests`): 11 tests — la app arranca y
   `/health` responde con el esquema esperado, las 5 `tools` tienen
   firma/docstring completos y levantan `NotImplementedError`, las 5 quedan
   registradas en el `MCPServer`, y `RespuestaAsistente` se construye y
   serializa. `python3 -m unittest discover -s asistente/tests -t .`: **11
   tests, todos en verde**. Suite completa del proyecto (`ingesta` + 258,
   `procesamiento` + 27, `asistente` + 11) sin regresiones.
5. **`asistente/requirements.txt`** y **`asistente/README.md`**.

## Decisión de SDK: `mcp` (paquete oficial), verificado instalándolo en vivo

Se instaló realmente el paquete (`pip install fastapi mcp httpx pytest`,
target aislado en `/tmp`, ~61MB, eliminado al terminar la tarea — no
commiteado ni dejado en el repo) para confirmar la API vigente en vez de
fiarse de memoria. Resultado relevante: la versión resuelta (2.0.0) expone
la clase de alto nivel para construir un servidor como `MCPServer`
(`mcp.server.mcpserver.server`), **no** `FastMCP` (`mcp.server.fastmcp`,
nombre de versiones anteriores del SDK, no presente en el paquete
instalado). Se verificó en vivo con instancias reales de `MCPServer` y
`add_tool()` que el registro de las 5 `tools`, la generación de su
`input_schema`/`output_schema` a partir de las anotaciones de tipo
(`datetime | None`, modelos Pydantic) y `list_tools()` funcionan como se
esperaba antes de escribir el código definitivo.

## Por qué el agente MCP no se monta en la app FastAPI todavía

`MCPServer.streamable_http_app()` devuelve una sub-app Starlette con su
propio ciclo de vida (gestor de sesiones HTTP), que montada con
`FastAPI.mount()` necesita combinar explícitamente su `lifespan` con el de
la app principal para arrancar/parar bien — un patrón real y documentado por
el propio SDK, pero que hoy no tendría nada que probar de verdad (las
`tools` no hacen nada). Se deja como paso explícito de la tarea que
implemente la primera `tool` real, documentado en el docstring de
`mcp_agent/server.py` y en `asistente/README.md`. Mientras tanto, el
servidor MCP es ejecutable de forma independiente en modo `stdio`
(`python -m asistente.mcp_agent.server`).

## Por qué no hay Terraform nuevo en esta tarea

A diferencia de Kafka (tarea 042) o Neo4j (tarea 043), donde ya existía una
pieza de infraestructura real que documentar aunque no se aplicara,
desplegar este esqueleto (un `/health` y `tools` que solo levantan
`NotImplementedError`) no tendría ningún efecto observable. Se decidió
escribir esa infraestructura (Lambda/ECS/EC2 + API Gateway para correr
FastAPI) cuando el servicio tenga al menos una `tool` real que sirva para
algo — documentado explícitamente como decisión (no como olvido) en
`asistente/README.md`, punto 5 de "Qué falta para completarlo".

## Verificación manual además de los tests

Se arrancó el servidor real (`uvicorn asistente.main:app`) en esta EC2 y se
confirmó con `curl` que `GET /health` devuelve
`{"status":"ok","servicio":"madrono-asistente","entorno":"development"}` y
que `GET /docs` (Swagger UI generado por FastAPI) responde `200` — no solo
`TestClient` en los tests, sino el proceso real sirviendo HTTP.

## Restricciones respetadas

- No se ha implementado ninguna lógica de negocio real ni se ha conectado a
  ninguna fuente de datos (Bronze, Silver ni Gold) — las 5 `tools` levantan
  `NotImplementedError`.
- No se ha desplegado nada en AWS — no se ha escrito ningún fichero `.tf`
  nuevo en esta tarea (decisión documentada arriba, no un olvido).
- No se ha capturado ninguna credencial real en ningún fichero commiteado.
- Las dependencias nuevas (`fastapi`, `mcp`, `httpx`, `uvicorn`) se
  instalaron en un directorio temporal fuera del repo (`/tmp/mcp_test_pkgs`,
  ~61MB) solo para verificar el código de esta tarea de forma real; se
  eliminó al terminar la sesión, no queda nada instalado de forma
  persistente en esta EC2 ni commiteado en el repo.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2:
  el servidor `uvicorn` de la verificación manual se lanzó en segundo plano
  con un `timeout` acotado y se detuvo al terminar la comprobación.

## Relevante para tareas futuras

- El bloqueante real para que las 5 `tools` dejen de ser esqueleto es que
  exista Gold para sus fuentes respectivas — hoy solo tráfico (doc/041). El
  patrón a seguir para extenderlo a las demás fuentes es el mismo que ya
  estableció esa tarea (`procesamiento/silver_gold/<dataset>/`).
  `asistente/README.md` incluye la tabla completa `tool` → dataset(s) de
  `ingesta/` de los que leería cada una.
- La versión instalada del SDK `mcp` (2.0.0) usa `MCPServer`, no `FastMCP`.
  Si una tarea futura sigue documentación o ejemplos que mencionan
  `mcp.server.fastmcp.FastMCP`, es probable que estén desactualizados
  respecto a lo que resuelve `pip install mcp` hoy — conviene volver a
  verificar en vivo en el momento, no asumir que el nombre de clase se ha
  mantenido.
- Montar el agente MCP dentro de la misma app FastAPI (combinando
  `lifespan`) y añadir el primer router HTTP real que use
  `RespuestaAsistente` son los dos siguientes pasos naturales una vez exista
  al menos una `tool` real, ver los puntos 3-4 de "Qué falta para
  completarlo" en `asistente/README.md`.
