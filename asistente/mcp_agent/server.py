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

from collections.abc import Callable
from typing import NamedTuple

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
    "lectura real.\n"
    "- Cuando no se indica un momento, el asistente se ancla a un día con "
    "datos reales (`ASSISTANT_ANCHOR_DATE`, uno de los 3 días curados que "
    "muestra el mapa: 2026-08-19 laborable / 2026-08-23 domingo / 2026-08-26 "
    "miércoles cargado). Para consultar otro de esos días, pásalo como "
    "`momento` (p. ej. `2026-08-23T18:00`)."
)

class ToolSpec(NamedTuple):
    """Una fila del registro único de tools.

    - ``fn``: la función real de `asistente/mcp_agent/tools.py`.
    - ``titulo``: etiqueta legible para el cliente MCP (Claude Desktop…).
    - ``desc_chat``: frase corta para el `tool-calling` del LLM del chat
      (`asistente/chat.py`) — los docstrings largos de MCP no caben en el
      límite de tokens del tier gratuito.
    - ``en_chat``: si se ofrece al LLM del chat. El chat expone solo un
      subconjunto (conversacional / graph-first) para no gastar el
      presupuesto TPM en esquemas grandes de dominio de nicho.
    - ``ejemplo_chat``: pregunta de ejemplo en lenguaje natural para el
      catálogo «¿qué puedo preguntar?» (`GET /chat/catalogo`, FIL_95).
      Cadena vacía = no aparece en el catálogo. Solo tiene sentido con
      ``en_chat=True``.
    """

    fn: Callable[..., object]
    titulo: str
    desc_chat: str
    en_chat: bool
    ejemplo_chat: str = ""


# Registro único de las tools del asistente. **Fuente de verdad** para: el
# servidor MCP (`add_tool` más abajo), los routers HTTP, la tabla de los
# README (`asistente/gen_tabla_tools.py`), el `tools=[...]` y la puerta de
# `_ejecutar_tool` del chat (`asistente/chat.py`) y los tests de conteo.
# Añadir una tool = una línea aquí y nada más (FIL_93 unificó el número;
# FIL_71 trajo `desc_chat`/`en_chat`, antes copiados a mano en `chat.py`).
_TOOLS = (
    ToolSpec(tools.afluencia_estimada, "Afluencia estimada ahora",
             "Actividad urbana estimada ahora cerca de un lugar (tráfico, ruido, BiciMAD, aire).", False),
    ToolSpec(tools.afluencia_prevista, "Afluencia prevista",
             "Afluencia prevista cerca de un lugar a un horizonte de 1, 3 o 6 horas.", False),
    ToolSpec(tools.calidad_aire, "Calidad del aire ahora",
             "Calidad del aire medida ahora en una zona o estación de Madrid.", True,
             "¿Cómo está la calidad del aire en Retiro?"),
    ToolSpec(tools.calidad_aire_prevista, "Calidad del aire prevista",
             "Previsión de calidad del aire (modelo LightGBM) a 1, 3 o 6 horas.", False),
    ToolSpec(tools.calidad_aire_prevista_grafo, "Calidad del aire prevista (modelo de grafo)",
             "Previsión de calidad del aire con el modelo de grafo (STGNN), con vecinos influyentes.", False),
    ToolSpec(tools.calidad_aire_episodio, "Probabilidad de episodio de contaminación",
             "Probabilidad de episodio (superar el umbral OMS/UE) del contaminante más crítico de una estación a 1/3/6 h.", True,
             "¿Hay riesgo de episodio de contaminación cerca de Plaza Elíptica en las próximas horas?"),
    ToolSpec(tools.calidad_aire_cams, "Calidad del aire previsión Copernicus CAMS",
             "Previsión de calidad del aire del modelo Copernicus CAMS (nivel ciudad) para un contaminante — segunda opinión independiente.", False),
    ToolSpec(tools.meteo_cercana, "Meteorología observada cerca de un lugar",
             "Meteorología observada (temperatura, viento, precipitación, humedad) en la estación más cercana a un lugar.", True,
             "¿Qué temperatura y viento hace ahora cerca de Chamartín?"),
    ToolSpec(tools.avisos_meteo, "Avisos meteorológicos AEMET",
             "Avisos meteorológicos AEMET activos en Madrid (nivel amarillo/naranja/rojo y fenómenos).", True,
             "¿Hay algún aviso meteorológico activo en Madrid?"),
    ToolSpec(tools.trafico_cercano, "Tráfico cerca de un lugar",
             "Tráfico medido ahora cerca de un lugar de Madrid.", True,
             "¿Cómo está el tráfico cerca de Atocha ahora?"),
    ToolSpec(tools.trafico_prevista, "Tráfico previsto",
             "Previsión de tráfico (modelo LightGBM) a 1, 3 o 6 horas cerca de un lugar.", False),
    ToolSpec(tools.trafico_prevista_grafo, "Tráfico previsto (modelo de grafo)",
             "Previsión de tráfico con el modelo de grafo (STGNN).", False),
    ToolSpec(tools.opciones_movilidad, "Opciones de movilidad entre dos puntos",
             "Compara ir en coche/bici/transporte público entre dos lugares.", False),
    ToolSpec(tools.disponibilidad_aparcamiento, "Disponibilidad de aparcamiento",
             "Plazas de aparcamiento regulado disponibles cerca de un lugar.", True,
             "¿Hay plazas de aparcamiento regulado libres cerca de Sol?"),
    ToolSpec(tools.eventos_cercanos, "Eventos cercanos",
             "Eventos culturales y de ocio cerca de un lugar en los próximos días.", True,
             "¿Qué eventos hay cerca de Gran Vía estos días?"),
    ToolSpec(tools.ruta_saludable, "Ruta saludable entre dos lugares",
             "Ruta que minimiza la exposición a tráfico/aire/ruido entre dos lugares, vs. la más rápida.", True,
             "Dame una ruta saludable de Sol a Atocha para alguien con asma"),
    ToolSpec(tools.contexto_urbano, "Contexto urbano multi-salto de un lugar",
             "Resumen del contexto urbano (distrito, lugares, estaciones) alrededor de un punto.", True,
             "¿Qué hay alrededor de Nuevos Ministerios?"),
    ToolSpec(tools.consulta_grafo, "Consulta parametrizada del grafo urbano (Neo4j)",
             "Consulta de solo lectura al grafo urbano de Neo4j mediante plantillas predefinidas (`plantilla`): "
             "estaciones de aire que miden un contaminante cerca de un lugar, paradas/líneas de transporte, "
             "aparcamientos, BiciMAD, vecindario de un lugar, etc.", True,
             "¿Qué estación de aire cerca de Retiro mide O₃?"),
    ToolSpec(tools.mejor_hora_zona, "Mejor hora del día para una zona",
             "Mejor hora del día para estar en una zona según una métrica (aire, ruido, tráfico).", True,
             "¿Cuál es la mejor hora para pasear por Chamberí hoy?"),
)
# Alias públicos (sin guion bajo) para importar desde fuera sin depender de
# un nombre "privado": el generador de la tabla, el chat y los tests leen de aquí.
TOOLS = _TOOLS
NOMBRES_TOOLS = tuple(s.fn.__name__ for s in _TOOLS)
# Subconjunto que el chat ofrece a su LLM, y sus frases cortas — antes eran
# `_TOOLS_CHAT` / `_DESCRIPCIONES` a mano en `asistente/chat.py` (FIL_70
# encontró el fallo típico: una tool en la lista de una y no de la otra).
NOMBRES_CHAT = frozenset(s.fn.__name__ for s in _TOOLS if s.en_chat)
DESCRIPCIONES_CHAT = {s.fn.__name__: s.desc_chat for s in _TOOLS}
# Catálogo «¿qué puedo preguntar?» (FIL_95): una entrada por tool del chat
# con ejemplo, en el orden del registro. Lo sirve `GET /chat/catalogo` y lo
# consumen la landing y el mapa para no hardcodear sugerencias que se
# desincronicen del registro (misma lección que FIL_70/FIL_71).
CATALOGO_CHAT = tuple(
    {"tool": s.fn.__name__, "titulo": s.titulo, "descripcion": s.desc_chat,
     "ejemplo": s.ejemplo_chat}
    for s in _TOOLS if s.en_chat and s.ejemplo_chat
)

# Todas las tools sólo LEEN (SELECT en Athena / MATCH en Neo4j / inferencia
# ONNX / Dijkstra o barrido sobre un grafo vendorizado): `read_only_hint=True`.
# `open_world_hint=True` porque consultan datos vivos externos. Son la señal
# estándar de "es seguro llamar a esto" para el cliente.
_ANOTACIONES_LECTURA = ToolAnnotations(read_only_hint=True, open_world_hint=True)

mcp = MCPServer(
    name="madrono",
    title="Madroño",
    instructions=_INSTRUCCIONES,
    description=(
        "Asistente conversacional sobre movilidad y vida urbana de Madrid "
        f"(memoria del TFM, apartados 5.2 y 6.7). {len(_TOOLS)} tools con lógica real: "
        "`calidad_aire` / `disponibilidad_aparcamiento` leen Gold vía Athena; "
        "`trafico_cercano` / `afluencia_estimada` / `eventos_cercanos` / "
        "`opciones_movilidad` cruzan el grafo urbano en Neo4j; "
        "`calidad_aire_prevista` (ML_09) y `trafico_prevista` (FIL_13) sirven "
        "una previsión desde los modelos ONNX de ML_07, `afluencia_prevista` "
        "(FIL_14) la deriva de ambas + persistencia, y "
        "`calidad_aire_prevista_grafo` / `trafico_prevista_grafo` (FIL_26/31) "
        "las sirven desde los STGNN de grafo (ML_05) con importancia de "
        "aristas, `ruta_saludable` enruta sobre el grafo minimizando "
        "exposición prevista (FIL_37), `contexto_urbano` hace una consulta "
        "multi-salto del grafo urbano (FIL_53) y `mejor_hora_zona` da la "
        "franja del día más limpia en un distrito por perfil de sensibilidad "
        "(FIL_46), `calidad_aire_episodio` da la probabilidad de superar el "
        "umbral OMS/UE del contaminante más crítico (FIL_79) y "
        "`calidad_aire_cams` trae la previsión de Copernicus CAMS como "
        "segunda opinión independiente (FIL_80), `meteo_cercana` da la "
        "meteorología observada junto a un lugar y `avisos_meteo` los "
        "avisos AEMET activos (FIL_82), y `consulta_grafo` da acceso "
        "directo a 8 plantillas de solo lectura sobre el grafo urbano de "
        "Neo4j (FIL_67) para preguntas relacionales que no encajan en "
        "ninguna otra tool. Ver asistente/mcp_agent/tools.py."
    ),
)

for _spec in _TOOLS:
    mcp.add_tool(_spec.fn, title=_spec.titulo, annotations=_ANOTACIONES_LECTURA)


def main() -> None:
    """Arranca el servidor MCP en modo `stdio` (uso en desarrollo)."""
    mcp.run()


if __name__ == "__main__":
    main()
