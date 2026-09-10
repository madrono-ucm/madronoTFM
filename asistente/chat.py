"""FIL_62/M2 — chat en lenguaje natural sobre las 19 tools de
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
import re
import time
from typing import Any

from groq import Groq

from asistente.mcp_agent import tools as tools_module
from asistente.mcp_agent.server import DESCRIPCIONES_CHAT, NOMBRES_CHAT, mcp

logger = logging.getLogger(__name__)

# Modelo por defecto: `qwen/qwen3.8-27b` en Groq (tier gratuito). Se eligió
# sobre `openai/gpt-oss-120b` porque este último, en pruebas en vivo (FIL_70),
# alucinaba nombres de tool e intentaba llamar herramientas en la ronda de
# redacción -> `400 tool_use_failed` y respuestas vacías. Qwen3 sigue el
# bucle de tool-calling de forma estable. Sigue con el límite de 8K TPM de
# Groq gratuito; ver `_TOOLS_CHAT` (subconjunto) y `_completar` (reintento).
#
# Proveedor configurable por entorno (FIL_70): apunta `LLM_BASE_URL` a otro
# endpoint OpenAI-compatible + `LLM_MODEL` + `LLM_API_KEY`, sin tocar código.
# Alternativas gratuitas con mejor tool-calling: Google Gemini
# (`https://generativelanguage.googleapis.com/v1beta/openai/`,
# `gemini-2.0-flash` -- tier gratuito generoso), OpenRouter modelos `:free`,
# o vLLM/Ollama propios. Cerebras NO tiene tier gratuito.
_MODEL = os.environ.get("LLM_MODEL", "qwen/qwen3.8-27b")
_LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or None
_MAX_TOKENS_RESPUESTA = 700
_MAX_REINTENTOS_LLM = 3
_ESTADOS_REINTENTABLES = {408, 409, 429, 500, 502, 503, 504, 529}
_SSM_PARAMETER = "/madrono-tfm/dev/secrets/groq-api-key"

# El chat solo expone un subconjunto de las tools MCP: las conversacionales y
# graph-first (fuera las `*_prevista*` / `afluencia_*` / `opciones_movilidad`:
# esquemas grandes, dominio de nicho, datos congelados -- así el `tools=[...]`
# ocupa ~la mitad de tokens y se aleja del límite TPM del tier gratuito). El
# subconjunto y su frase corta viven en el registro único
# `asistente/mcp_agent/server.py` (`en_chat` / `desc_chat` de cada `ToolSpec`);
# FIL_70 encontró el fallo típico de tenerlo en dos listas a mano que se
# desincronizan.
_TOOLS_CHAT = NOMBRES_CHAT

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

# Descripción corta por tool (una frase, para el tool-calling del LLM): del
# registro único `server.DESCRIPCIONES_CHAT`. El `input_schema` real
# (parámetros) se toma en vivo de `mcp.list_tools()`, no se duplica.
_DESCRIPCIONES = DESCRIPCIONES_CHAT

_client: "Groq | None" = None
_tools_schema: "list[dict] | None" = None


def _leer_api_key() -> str:
    """Prioridad: `LLM_API_KEY` / `GROQ_API_KEY` en el entorno (tests /
    desarrollo local / proveedor alternativo) -> SSM SecureString
    (producción, misma EC2/rol que lee el resto de secretos -- ver
    `ingesta/capturas/secretos.py`)."""
    env = os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY")
    if env:
        return env
    import boto3

    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
    resp = ssm.get_parameter(Name=_SSM_PARAMETER, WithDecryption=True)
    return resp["Parameter"]["Value"]


def _cliente():
    """Cliente de chat. Por defecto el SDK de Groq. Si se define
    `LLM_BASE_URL` y `openai` está instalado, se usa `openai.OpenAI`
    (transporte OpenAI-compatible más estándar para proveedores no-Groq como
    Gemini/OpenRouter); si `openai` no está, se cae al SDK de Groq con
    `base_url` (funciona con la mayoría de endpoints compatibles)."""
    global _client
    if _client is not None:
        return _client
    key = _leer_api_key()
    if _LLM_BASE_URL:
        try:
            from openai import OpenAI

            _client = OpenAI(api_key=key, base_url=_LLM_BASE_URL)
            return _client
        except ImportError:
            logger.info("`openai` no instalado; uso el SDK de Groq con base_url=%s", _LLM_BASE_URL)
    _client = Groq(api_key=key, base_url=_LLM_BASE_URL)
    return _client


def _completar(client, **kwargs):
    """`chat.completions.create` con reintento ante 429 / 5xx / timeout
    (backoff exponencial corto). Un error no reintentable (400, auth...) se
    propaga en el primer intento."""
    for intento in range(_MAX_REINTENTOS_LLM):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            estado = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if intento == _MAX_REINTENTOS_LLM - 1 or (
                estado is not None and estado not in _ESTADOS_REINTENTABLES
            ):
                raise
            logger.info("reintento %d de la llamada al LLM (%s)", intento + 1, exc)
            time.sleep(1.2 * (2 ** intento))


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
        if t.name not in _TOOLS_CHAT:
            continue
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


# Centinelas de "sin datos" que cada tool usa a su manera (histórico: no hay
# un contrato común todavía -- eso es FIL_71 completo, post-entrega). El chat
# los traduce a un único `disponible=false` + `motivo` para que el LLM no
# tenga que reconocer cada variante.
_CLAVES_CENTINELA = ("indice_calidad", "resumen", "nivel", "estado", "nivel_trafico")


def _normalizar_resultado(payload: Any) -> "dict[str, Any]":
    """Envuelve el retorno de una tool en `{disponible, motivo, datos}`.

    `disponible=False` cuando la propia tool ya se declara degradada
    (`disponible: false` + `motivo`, de las `*_prevista`, FIL_15) o marca
    "sin datos" con uno de sus centinelas; si no, `True`. Así el LLM ve
    siempre la misma forma y el `_SYSTEM_PROMPT` ("si no hay datos, dilo")
    tiene una señal fiable en la que apoyarse.
    """
    datos = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    disponible, motivo = True, None
    if isinstance(datos, dict):
        if datos.get("disponible") is False:
            disponible = False
            motivo = datos.get("motivo") or "la herramienta se declaró no disponible"
        elif any(datos.get(k) == "sin_datos" for k in _CLAVES_CENTINELA):
            disponible = False
            motivo = "sin datos para la consulta (zona sin cobertura o fuera de la ventana disponible)"
    return {"disponible": disponible, "motivo": motivo, "datos": datos}


def _ejecutar_tool(nombre: str, args: dict) -> "dict[str, Any]":
    """Llama a la tool real en proceso (la misma función que usan MCP/HTTP) y
    devuelve SIEMPRE `{disponible, motivo, datos}` -- nunca lanza y nunca
    inventa una forma propia de error. Toda tool ofrecida al LLM
    (`server.NOMBRES_CHAT`) es ejecutable aquí; lo contrario era el bucle
    "herramienta desconocida" de FIL_70."""
    if nombre not in _TOOLS_CHAT:
        return {"disponible": False, "motivo": f"herramienta no disponible en el chat: {nombre!r}", "datos": None}
    fn = getattr(tools_module, nombre, None)
    if fn is None:  # registrada pero sin función importable: no debería ocurrir
        return {"disponible": False, "motivo": f"herramienta desconocida: {nombre!r}", "datos": None}
    try:
        resultado = fn(**args)
    except Exception as exc:  # noqa: BLE001 - degradación elegante, ver docstring
        logger.warning("fallo ejecutando tool %s(%r): %s", nombre, args, exc)
        return {"disponible": False, "motivo": f"fallo al consultar {nombre}: {exc}", "datos": None}
    return _normalizar_resultado(resultado)


def _extraer_tool_calls(msg) -> list:
    return list(getattr(msg, "tool_calls", None) or [])


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _sin_think(texto):
    """Quita bloques `<think>...</think>` (algunos modelos de razonamiento
    los filtran a la salida). `None` -> `None`."""
    return _THINK_RE.sub("", texto).strip() if texto else texto


_MAX_RONDAS_TOOL = 4


def chat(mensaje: str, historial: "list[dict] | None" = None) -> dict:
    """Un turno de chat como bucle acotado de tool-calling (formato
    Groq/OpenAI). `historial` es la lista de mensajes previa (vacía en el
    primer turno); se devuelve `{"respuesta": str, "historial": list[dict]}`
    y el `historial` devuelto se reenvía tal cual al siguiente turno.

    El bucle (hasta `_MAX_RONDAS_TOOL` rondas con herramientas + 1 ronda
    final en prosa) tolera que el modelo alucine un nombre de tool
    (`_ejecutar_tool` devuelve un error que el modelo puede corregir) o
    intente llamar una tool en la ronda de redacción (400
    `tool_use_failed` de Groq -> se fuerza prosa)."""
    client = _cliente()
    tools = _tools_para_groq()

    messages: "list[dict]" = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(historial or [])
    messages.append({"role": "user", "content": mensaje})

    def _degradado(msg_err: str):
        base = messages if len(messages) > 2 else (historial or [])
        return {"respuesta": msg_err, "historial": base}

    for ronda in range(_MAX_RONDAS_TOOL + 1):
        ultima = ronda == _MAX_RONDAS_TOOL
        kw = dict(model=_MODEL, messages=messages,
                  max_tokens=_MAX_TOKENS_RESPUESTA, temperature=0.2)
        if not ultima:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"

        try:
            resp = _completar(client, **kw)
        except Exception as exc:  # noqa: BLE001
            estado = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None)
            if estado == 400 and "tool" in str(exc).lower() and not ultima:
                logger.info("tool_use_failed en ronda %d -> forzar prosa", ronda)
                messages.append({"role": "system",
                                 "content": "Responde ahora en prosa, sin llamar más herramientas."})
                try:
                    resp = _completar(client, model=_MODEL, messages=messages,
                                      max_tokens=_MAX_TOKENS_RESPUESTA, temperature=0.2)
                except Exception as exc2:  # noqa: BLE001
                    logger.warning("fallo redactando (fallback prosa): %s", exc2)
                    return _degradado("He consultado los datos pero no he podido redactar la respuesta (fallo del modelo).")
            else:
                logger.warning("fallo llamando al LLM (ronda %d): %s", ronda, exc)
                return _degradado("No he podido consultar el modelo ahora mismo (límite de peticiones o fallo temporal). Prueba de nuevo en un momento.")

        msg = resp.choices[0].message
        tcs = _extraer_tool_calls(msg)

        if not tcs or ultima:
            texto = _sin_think(msg.content) or "He consultado los datos, pero el modelo no ha devuelto texto."
            messages.append({"role": "assistant", "content": texto})
            return {"respuesta": texto, "historial": messages}

        messages.append({
            "role": "assistant", "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tcs
            ],
        })
        for tc in tcs:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            resultado = _ejecutar_tool(tc.function.name, args)
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(resultado, ensure_ascii=False, default=str),
            })

    return _degradado("No he podido completar la consulta.")  # inalcanzable en la práctica
