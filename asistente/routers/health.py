"""Endpoint de salud del servicio.

Único endpoint funcional de esta tarea (el resto del servicio es esqueleto,
ver `asistente/README.md`): confirma que el proceso FastAPI arrancó y puede
resolver dependencias, sin comprobar ninguna fuente de datos externa (no hay
ninguna todavía).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from asistente.dependencies import SettingsDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    servicio: str = "madrono-asistente"
    entorno: str
    # FIL_73: contadores del chat acumulados en proceso (tool-calls totales /
    # con error, llamadas al LLM, 429 servidos). Útiles para ver de un
    # vistazo si el tier gratuito del LLM se está quedando corto.
    chat: dict = {}


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    try:
        from asistente.chat import metricas

        chat = metricas()
    except Exception:  # noqa: BLE001 - health nunca falla por esto
        chat = {}
    return HealthResponse(entorno=settings.environment, chat=chat)
