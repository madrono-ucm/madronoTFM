"""Endpoint HTTP `/chat` — FIL_62/M2: chat en lenguaje natural sobre las
tools del asistente, vía Groq. Ver `asistente/chat.py` para la
orquestación real (tool-calling, ejecución de tools, redacción de la
respuesta).
"""

from __future__ import annotations

from typing import Any

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


class RespuestaChat(BaseModel):
    respuesta: str
    historial: "list[dict[str, Any]]"


@router.post("/chat", response_model=RespuestaChat)
def conversar(peticion: PeticionChat) -> RespuestaChat:
    resultado = chat_module.chat(peticion.mensaje, peticion.historial)
    return RespuestaChat(**resultado)
