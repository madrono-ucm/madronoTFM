"""Zona horaria de Madrid, reutilizada en los timestamps de este servicio.

Mismo patrón que `ingesta.capturas.bronze.now_madrid()` (tarea 034): se usa
`zoneinfo` (librería estándar, sin dependencias de terceros) en vez de un
offset fijo, para que el desfase aplicado sea el real según la época del año
(CET/UTC+1 en invierno, CEST/UTC+2 en verano). No se importa directamente
`ingesta.capturas.bronze` para mantener `asistente/` como un servicio
autocontenido, desplegable de forma independiente de `ingesta/`.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")


def now_madrid() -> datetime:
    """Devuelve el instante actual como `datetime` *aware* en hora de Madrid."""
    return datetime.now(MADRID_TZ)
