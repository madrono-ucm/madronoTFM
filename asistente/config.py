"""Configuración del servicio, leída de variables de entorno.

Mismo patrón que `ingesta.capturas.trafico_madrid.CaptureConfig` (dataclass +
`from_env()`, sin dependencias adicionales como `pydantic-settings`): este
proyecto ya usa esa convención en `ingesta/`, y no hay motivo para introducir
una segunda forma de leer configuración en `asistente/`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Configuración del servicio.

    `gold_base_path` es, a propósito, un valor que hoy no lee nadie: ninguna
    `tool` del agente MCP tiene todavía lógica real (ver
    `asistente/mcp_agent/tools.py`), así que no hay ningún sitio del que leer
    Gold aún. Se deja definida aquí, con el mismo nombre de variable de
    entorno que usaría el resto del proyecto (`BRONZE_BASE_PATH` en
    `ingesta/`, ver `ingesta/capturas/trafico_madrid.py`), para que quien
    complete las `tools` en una tarea futura tenga ya el punto de entrada de
    configuración listo, en vez de tener que decidir de nuevo cómo se
    configura el servicio.
    """

    environment: str
    log_level: str
    gold_base_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.environ.get("ASISTENTE_ENVIRONMENT", "development"),
            log_level=os.environ.get("ASISTENTE_LOG_LEVEL", "INFO"),
            gold_base_path=os.environ.get("GOLD_BASE_PATH", "./gold"),
        )
