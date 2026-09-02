"""FIL_62/M2 — chat en lenguaje natural sobre las 14 tools de
`asistente/mcp_agent/tools.py`, vía Groq (API compatible con OpenAI,
`tool_use`; tier gratuito, ver `FIL_62` para el porqué de Groq frente a
auto-hospedar un LLM en esta misma EC2).

Groq decide qué tool(s) llamar a partir del mensaje libre del usuario;
este módulo ejecuta la(s) tool(s) elegida(s) directamente en proceso
(las mismas funciones de `tools.py`, sin pasar por HTTP) y le devuelve el
resultado a Groq para que redacte la respuesta final en prosa.

Las descripciones de las tools que se le pasan a Groq **no son los
docstrings completos** de `tools.py` (pensados para MCP/Claude Desktop,
~2.000 caracteres cada uno, ~7.000 tokens los 14 juntos -- más de la
mitad del límite de 12.000 TPM del tier gratuito de Groq para
`llama-3.3-70b-versatile`). Aquí se usa una descripción corta por tool,
de una frase, y el `input_schema` real (compacto, ~1.200 tokens los 14)
tomado en vivo del propio servidor MCP -- una sola fuente de verdad para
los parámetros, sin duplicarlos a mano.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from groq import Groq

from asistente.mcp_agent import tools as tools_module
from asistente.mcp_agent.server import mcp

logger = logging.getLogger(__name__)

# `llama-3.3-70b-versatile` (elegido en `FIL_62`) ya no está en el
# catálogo de Groq en el momento de implementar esto (verificado en vivo
# con `client.models.list()`) -- el catálogo gratuito de Groq rota. Se usa
# `openai/gpt-oss-120b` (activo hoy, tool-calling real, dentro del tier
# gratuito: 30 RPM / 1.000 RPD / 8K TPM / 200K TPD según la investigación
# de `FIL_62`) -- mismo criterio de "el modelo concreto no importa mucho".
_MODEL = "openai/gpt-oss-120b"
_MAX_TOKENS_RESPUESTA = 700
_SSM_PARAMETER = "/madrono-tfm/dev/secrets/groq-api-key"

_SYSTEM_PROMPT = (
    "Eres Madroño, el asistente de una plataforma de datos abiertos de "
    "Madrid (tráfico, calidad del aire, ruido, movilidad, aparcamiento, "
    "eventos). Respondes siempre en español, de forma breve y concreta. "
    "Basas cada respuesta únicamente en lo que devuelven las herramientas "
    "-- nunca inventes una cifra ni una estación que no aparezca en el "
    "resultado. Si una herramienta no encuentra datos, dilo con claridad "
    "en vez de suponer. Los datos son de código abierto del Ayuntamiento "
    "de Madrid; no das consejo médico ni tratas datos personales."
)

# Descripción corta por tool (una frase, para el tool-calling de Groq) --
# el `input_schema` real (parámetros) se toma en vivo de `mcp.list_tools()`,
# no se duplica aquí.
_DESCRIPCIONES = {
    "afluencia_estimada": "Actividad urbana estimada ahora cerca de un lugar (tráfico, ruido, BiciMAD, aire).",
    "afluencia_prevista": "Afluencia prevista cerca de un lugar a un horizonte de 1, 3 o 6 horas.",
    "calidad_aire": "Calidad del aire medida ahora en una zona o estación de Madrid.",
    "calidad_aire_prevista": "Previsión de calidad del aire (modelo LightGBM) a 1, 3 o 6 horas.",
    "calidad_aire_prevista_grafo": "Previsión de calidad del aire con el modelo de grafo (STGNN), con vecinos influyentes.",
    "trafico_cercano": "Tráfico medido ahora cerca de un lugar de Madrid.",
    "trafico_prevista": "Previsión de tráfico (modelo LightGBM) a 1, 3 o 6 horas cerca de un lugar.",
    "trafico_prevista_grafo": "Previsión de tráfico con el modelo de grafo (STGNN).",
    "opciones_movilidad": "Compara ir en coche/bici/transporte público entre dos lugares.",
    "disponibilidad_aparcamiento": "Plazas de aparcamiento regulado disponibles cerca de un lugar.",
    "eventos_cercanos": "Eventos culturales y de ocio cerca de un lugar en los próximos días.",
    "ruta_saludable": "Ruta que minimiza la exposición a tráfico/aire/ruido entre dos lugares, vs. la más rápida.",
    "contexto_urbano": "Resumen del contexto urbano (distrito, lugares, estaciones) alrededor de un punto.",
    "mejor_hora_zona": "Mejor hora del día para estar en una zona según una métrica (aire, ruido, tráfico).",
}

_client: "Groq | None" = None
_tools_schema: "list[dict] | None" = None


def _leer_api_key() -> str:
    """Prioridad: `GROQ_API_KEY` en el entorno (tests/desarrollo local) ->
    SSM SecureString (producción, misma EC2/rol que ya lee el resto de
    secretos del proyecto -- ver `ingesta/capturas/secretos.py`)."""
    env = os.environ.get("GROQ_API_KEY")
    if env:
        return env
    import boto3

    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
    resp = ssm.get_parameter(Name=_SSM_PARAMETER, WithDecryption=True)
    return resp["Parameter"]["Value"]


def _cliente() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=_leer_api_key())
    return _client


def _tools_para_groq() -> "list[dict]":
    """Construye el `tools=[...]` de Groq: descripción corta (arriba) +
    `input_schema` real tomado en vivo de `mcp.list_tools()` -- una sola
    fuente de verdad para los parámetros, cacheado tras la primera llamada
    (el registro de tools no cambia en caliente)."""
    global _tools_schema
    if _tools_schema is not None:
        return _tools_schema

    async def _listar():
        return await mcp.list_tools()

    listado = asyncio.run(_listar())
    out = []
    for t in listado:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": _DESCRIPCIONES.get(t.name, t.name),
                    "parameters": t.input_schema,
                },
            }
        )
    _tools_schema = out
    return out


def _ejecutar_tool(nombre: str, args: dict) -> Any:
    """Llama a la tool real en proceso (misma función que MCP/HTTP usan) y
    serializa el resultado a algo JSON-able. Nunca lanza -- una tool con
    error se convierte en un mensaje de error para que Groq lo explique,
    mismo criterio de degradación elegante que el resto de `asistente/`."""
    fn = getattr(tools_module, nombre, None)
    if fn is None or nombre not in _DESCRIPCIONES:
        return {"error": f"herramienta desconocida: {nombre!r}"}
    try:
        resultado = fn(**args)
    except Exception as exc:  # noqa: BLE001 - degradación elegante, ver docstring
        logger.warning("fallo ejecutando tool %s(%r): %s", nombre, args, exc)
        return {"error": f"fallo al consultar {nombre}: {exc}"}
    if hasattr(resultado, "model_dump"):
        return resultado.model_dump(mode="json")
    return resultado


def chat(mensaje: str, historial: "list[dict] | None" = None) -> dict:
    """Un turno de chat. `historial` es la lista de mensajes previa (formato
    Groq/OpenAI: `{"role": ..., "content": ...}`), vacía en el primer turno.
    Devuelve `{"respuesta": str, "historial": list[dict]}` -- el `historial`
    devuelto se le pasa tal cual al siguiente turno (el front no necesita
    entender su estructura interna, solo guardarlo y reenviarlo)."""
    client = _cliente()
    tools = _tools_para_groq()

    messages: "list[dict]" = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(historial or [])
    messages.append({"role": "user", "content": mensaje})

    try:
        resp = client.chat.completions.create(
            model=_MODEL, messages=messages, tools=tools, tool_choice="auto",
            max_tokens=_MAX_TOKENS_RESPUESTA, temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001 - degradación elegante (429/5xx de Groq)
        logger.warning("fallo llamando a Groq: %s", exc)
        return {
            "respuesta": "No he podido consultar el modelo ahora mismo (límite de peticiones o fallo temporal de Groq). Prueba de nuevo en un momento.",
            "historial": historial or [],
        }

    msg = resp.choices[0].message
    tool_calls = msg.tool_calls or []

    if not tool_calls:
        messages.append({"role": "assistant", "content": msg.content})
        return {"respuesta": msg.content, "historial": messages}

    messages.append(
        {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        }
    )
    for tc in tool_calls:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        resultado = _ejecutar_tool(tc.function.name, args)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(resultado, ensure_ascii=False, default=str),
            }
        )

    try:
        resp2 = client.chat.completions.create(
            model=_MODEL, messages=messages, max_tokens=_MAX_TOKENS_RESPUESTA, temperature=0.2,
        )
        respuesta = resp2.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 - degradación elegante
        logger.warning("fallo redactando la respuesta final: %s", exc)
        respuesta = "He consultado los datos pero no he podido redactar la respuesta (fallo temporal de Groq)."

    messages.append({"role": "assistant", "content": respuesta})
    return {"respuesta": respuesta, "historial": messages}
