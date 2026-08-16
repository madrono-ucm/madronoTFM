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


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(entorno=settings.environment)
