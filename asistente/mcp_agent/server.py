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

Por qué esto no se monta todavía en la app FastAPI (`asistente/main.py`):
`MCPServer.streamable_http_app()` devuelve una sub-app Starlette con su
propio ciclo de vida (gestiona sesiones vía `StreamableHTTPSessionManager`),
que al montarse con `FastAPI.mount()` necesita combinarse explícitamente con
el `lifespan` de la app principal (patrón documentado por el propio SDK,
vía `contextlib.AsyncExitStack`) para que el gestor de sesiones arranque y
pare correctamente. Añadir esa integración ahora, con `tools` que no hacen
nada real todavía (`NotImplementedError`), sería infraestructura sin nada
que probar de verdad; se deja como paso explícito de la tarea que implemente
la primera `tool` real. Mientras tanto, este servidor es ejecutable de forma
independiente en modo `stdio` (`python -m asistente.mcp_agent.server`), la
forma estándar en que clientes MCP como Claude Desktop lo probarían en
desarrollo.
"""

from __future__ import annotations

from mcp.server.mcpserver.server import MCPServer

from asistente.mcp_agent import tools

mcp = MCPServer(
    name="madrono",
    title="Madroño",
    description=(
        "Asistente conversacional sobre movilidad y vida urbana de Madrid "
        "(memoria del TFM, apartados 5.2 y 6.7). Esqueleto: las tools "
        "todavía no leen datos reales, ver asistente/mcp_agent/tools.py."
    ),
)

for _tool in (
    tools.afluencia_prevista,
    tools.calidad_aire,
    tools.opciones_movilidad,
    tools.disponibilidad_aparcamiento,
    tools.eventos_cercanos,
):
    mcp.add_tool(_tool)


def main() -> None:
    """Arranca el servidor MCP en modo `stdio` (uso en desarrollo)."""
    mcp.run()


if __name__ == "__main__":
    main()
