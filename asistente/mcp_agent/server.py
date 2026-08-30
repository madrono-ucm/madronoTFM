"""Instancia del servidor MCP del asistente «Madroño» y registro de sus `tools`.

SDK elegido: el paquete oficial `mcp` (Model Context Protocol, mantenido por
Anthropic y la comunidad, https://github.com/modelcontextprocol/python-sdk)
en su versión instalada más reciente en el momento de esta tarea (2.0.0). Es
el estándar de facto para exponer `tools`/`resources`/`prompts` a agentes
LLM de forma interoperable — la alternativa habría sido definir un esquema
de herramientas ad-hoc consumido solo por un cliente propio, lo que ata el
asistente a una única integración en vez de a cualquier cliente MCP.

En esta versión del SDK, la clase de alto nivel para construir un servidor
MCP es `MCPServer` (`mcp.server.mcpserver.server.MCPServer`, verificado
importando el paquete instalado — versiones anteriores del SDK exponían la
misma idea bajo el nombre `FastMCP` en `mcp.server.fastmcp`, ya no presente
en el código instalado en esta tarea).

Las `tools` se definen como funciones planas en `asistente/mcp_agent/tools.py`
(testeables sin depender de esta instancia) y se registran aquí vía
`MCPServer.add_tool()`, en vez de decorarlas con `@mcp.tool()` directamente
en `tools.py` — así `tools.py` no depende de que este módulo (ni la propia
librería `mcp`) se pueda importar para que sus funciones sigan siendo
inspeccionables/testeables de forma aislada.

Tarea 081: `trafico_cercano` se registra junto a `calidad_aire` -- es la
primera `tool` que, además de Athena, consulta el grafo urbano real en Neo4j
(`asistente/neo4j_client.py`, ver doc/080).

Tarea 079: este servidor ya se monta en la app FastAPI
(`asistente/main.py::create_app`, vía `MCPServer.streamable_http_app()` +
`FastAPI.mount()`, con el `lifespan` de ambas apps combinado explícitamente
-- ver el docstring de `main.py` para el porqué). Sigue siendo también
ejecutable de forma independiente en modo `stdio`
(`python -m asistente.mcp_agent.server`), la forma estándar en que clientes
MCP como Claude Desktop lo probarían en desarrollo sin pasar por HTTP.
"""

from __future__ import annotations

from mcp.server.mcpserver.server import MCPServer
from mcp.types import ToolAnnotations

from asistente.mcp_agent import tools

# `instructions` es lo que el cliente MCP muestra a su LLM como "cómo/cuándo
# usar este servidor" (distinto de `description`, que es la ficha del
# servidor). Aquí van las tres cosas que un modelo necesita saber para no
# malinterpretar las respuestas.
_INSTRUCCIONES = (
    "Datos de movilidad y vida urbana de Madrid a partir de fuentes públicas "
    "municipales/estatales (tráfico, calidad del aire, ruido, BiciMAD, "
    "aparcamientos, EMT, eventos) más previsiones de modelos propios.\n"
    "\n"
    "Cómo usar las tools:\n"
    "- «lugar»/«zona» se resuelven por COINCIDENCIA DE TEXTO (no por "
    "dirección ni coordenadas): sobre el nombre de la estación para "
    "`calidad_aire`/`disponibilidad_aparcamiento`, sobre el nombre del nodo "
    "`:Lugar` del grafo urbano para el resto. Usa nombres de sitios "
    "reconocibles («Retiro», «Sol», «Atocha», «Plaza de España»).\n"
    "- Ninguna tool lanza excepción por falta de datos: devuelven un objeto "
    "con `indice_calidad`/`resumen`/`nivel_*` = «sin_datos» (o, en las "
    "`*_prevista`, `disponible=false` + `motivo`). Trata eso como «no hay "
    "información», no como un error.\n"
    "- Las `*_prevista` sirven una cifra desde un modelo ONNX; la ventana de "
    "entrenamiento es CORTA (semanas), así que son una demostración de "
    "metodología, no una predicción de rendimiento estacional. `fiabilidad` "
    "nunca pasa de «media» por eso.\n"
    "- Los índices/niveles («buena»/«regular»/«fluido»/«denso»…) son "
    "etiquetas SIMPLIFICADAS, no el ICA oficial ni una métrica normativa.\n"
    "- La ingesta está CONGELADA desde 2026-08-30: los datos llegan hasta "
    "~2026-08-29. Si se pide un momento posterior, se usa la última hora con "
    "lectura real."
)

mcp = MCPServer(
    name="madrono",
    title="Madroño",
    instructions=_INSTRUCCIONES,
    description=(
        "Asistente conversacional sobre movilidad y vida urbana de Madrid "
        "(memoria del TFM, apartados 5.2 y 6.7). 9 tools con lógica real: "
        "`calidad_aire` / `disponibilidad_aparcamiento` leen Gold vía Athena; "
        "`trafico_cercano` / `afluencia_estimada` / `eventos_cercanos` / "
        "`opciones_movilidad` cruzan el grafo urbano en Neo4j; "
        "`calidad_aire_prevista` (ML_09) y `trafico_prevista` (FIL_13) sirven "
        "una previsión desde los modelos ONNX de ML_07, y `afluencia_prevista` "
        "(FIL_14) la deriva de ambas + persistencia. Ver "
        "asistente/mcp_agent/tools.py."
    ),
)

# Las 9 tools sólo LEEN (SELECT en Athena / MATCH en Neo4j / inferencia ONNX):
# `read_only_hint=True`. `open_world_hint=True` porque consultan datos vivos
# externos. Son la señal estándar de "es seguro llamar a esto" para el cliente.
_ANOTACIONES_LECTURA = ToolAnnotations(read_only_hint=True, open_world_hint=True)

# `(función, título legible para el cliente)`.
_TOOLS = (
    (tools.afluencia_estimada, "Afluencia estimada ahora"),
    (tools.afluencia_prevista, "Afluencia prevista"),
    (tools.calidad_aire, "Calidad del aire ahora"),
    (tools.calidad_aire_prevista, "Calidad del aire prevista"),
    (tools.trafico_cercano, "Tráfico cerca de un lugar"),
    (tools.trafico_prevista, "Tráfico previsto"),
    (tools.opciones_movilidad, "Opciones de movilidad entre dos puntos"),
    (tools.disponibilidad_aparcamiento, "Disponibilidad de aparcamiento"),
    (tools.eventos_cercanos, "Eventos cercanos"),
)

for _fn, _titulo in _TOOLS:
    mcp.add_tool(_fn, title=_titulo, annotations=_ANOTACIONES_LECTURA)


def main() -> None:
    """Arranca el servidor MCP en modo `stdio` (uso en desarrollo)."""
    mcp.run()


if __name__ == "__main__":
    main()
