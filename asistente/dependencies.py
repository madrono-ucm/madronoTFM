"""Dependencias de FastAPI compartidas entre routers.

`get_settings` sigue el patrón estándar de FastAPI para configuración
cacheada (`functools.lru_cache` sobre una función sin argumentos, ver la
documentación oficial de FastAPI sobre "Settings and Environment
Variables"): cada `Settings.from_env()` real solo se calcula una vez por
proceso, y los tests pueden sustituir esta dependencia con
`app.dependency_overrides[get_settings]` sin tocar variables de entorno.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from asistente.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


SettingsDep = Annotated[Settings, Depends(get_settings)]
