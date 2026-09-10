"""Endpoint HTTP `/chat` — FIL_62/M2: chat en lenguaje natural sobre las
tools del asistente, vía Groq. Ver `asistente/chat.py` para la
orquestación real (tool-calling, ejecución de tools, redacción de la
respuesta).
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from asistente import chat as chat_module

router = APIRouter(tags=["chat"])


class PeticionChat(BaseModel):
    mensaje: str = Field(..., description="Mensaje del usuario, en lenguaje natural.")
    historial: "list[dict[str, Any]]" = Field(
        default_factory=list,
        description=(
            "Historial devuelto por la respuesta anterior (vacío en el primer "
            "turno) — el cliente solo lo guarda y lo reenvía tal cual, no "
            "necesita entender su estructura interna."
        ),
    )


class PasoChat(BaseModel):
    tool: str
    ok: bool
    ms: int
    filas: "int | None" = None


class RespuestaChat(BaseModel):
    respuesta: str
    historial: "list[dict[str, Any]]"
    # FIL_95: herramientas que ejecutó ESTE turno, en orden. Vacío = el
    # modelo respondió sin consultar datos. Es traza para enseñar al
    # usuario, no un contrato estable.
    pasos: "list[PasoChat]" = Field(default_factory=list)


class EntradaCatalogo(BaseModel):
    tool: str
    titulo: str
    descripcion: str
    ejemplo: str


@router.post("/chat", response_model=RespuestaChat)
def conversar(peticion: PeticionChat) -> RespuestaChat:
    resultado = chat_module.chat(peticion.mensaje, peticion.historial)
    return RespuestaChat(**resultado)


@router.get("/chat/catalogo", response_model=List[EntradaCatalogo])
def catalogo() -> "list[EntradaCatalogo]":
    """Catálogo «¿qué puedo preguntar?» — una entrada por herramienta que el
    chat ofrece al LLM, con un ejemplo en lenguaje natural. Sale del registro
    único de tools (`server.CATALOGO_CHAT`), así que la landing y el mapa no
    hardcodean sugerencias que se desincronicen (FIL_95)."""
    from asistente.mcp_agent.server import CATALOGO_CHAT

    return [EntradaCatalogo(**e) for e in CATALOGO_CHAT]
