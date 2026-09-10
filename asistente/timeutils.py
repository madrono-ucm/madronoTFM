"""Zona horaria de Madrid, reutilizada en los timestamps de este servicio.

Mismo patrón que `ingesta.capturas.bronze.now_madrid()` (tarea 034): se usa
`zoneinfo` (librería estándar, sin dependencias de terceros) en vez de un
offset fijo, para que el desfase aplicado sea el real según la época del año
(CET/UTC+1 en invierno, CEST/UTC+2 en verano). No se importa directamente
`ingesta.capturas.bronze` para mantener `asistente/` como un servicio
autocontenido, desplegable de forma independiente de `ingesta/`.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MADRID_TZ = ZoneInfo("Europe/Madrid")

# Los 3 días que el mapa animado (`viz/build_mapa_animado.py`) muestra y para
# los que hay datos reales en Gold: laborable normal / domingo tranquilo /
# miércoles cargado. La ingesta está CONGELADA desde 2026-08-30, así que
# "ahora" (real) cae fuera de la ventana con datos.
DIAS_CURADOS: tuple[str, ...] = ("2026-08-19", "2026-08-23", "2026-08-26")

# Fecha de anclaje del asistente: si se define `ASSISTANT_ANCHOR_DATE`
# (YYYY-MM-DD) en el entorno, las tools que no reciben un `momento` explícito
# la usan como "hoy" en vez del reloj real -> devuelven datos reales de la
# ventana congelada en vez de "sin datos". El despliegue la fija a un día
# curado (ver `infra/OPERACION.md`); en tests/desarrollo sin la env, se
# comporta como siempre (`now_madrid()`).
_ANCHOR_ENV = "ASSISTANT_ANCHOR_DATE"


def now_madrid() -> datetime:
    """Devuelve el instante actual como `datetime` *aware* en hora de Madrid."""
    return datetime.now(MADRID_TZ)


def fecha_ancla() -> "date | None":
    """`ASSISTANT_ANCHOR_DATE` parseada, o `None` si no está / es inválida."""
    raw = os.environ.get(_ANCHOR_ENV, "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("%s=%r no es una fecha ISO (YYYY-MM-DD); se ignora", _ANCHOR_ENV, raw)
        return None


def ahora_o_ancla() -> datetime:
    """Instante de referencia por defecto de las tools cuando el llamante no
    pasa `momento`: el reloj real, salvo que `ASSISTANT_ANCHOR_DATE` esté
    definida, en cuyo caso esa fecha con la hora-del-día actual (para que la
    dimensión "hora" siga variando de forma natural), en hora de Madrid."""
    ancla = fecha_ancla()
    ahora = now_madrid()
    if ancla is None:
        return ahora
    return ahora.replace(year=ancla.year, month=ancla.month, day=ancla.day)


def dia_curado_mas_cercano(d: "date | str") -> str:
    """El de `DIAS_CURADOS` más próximo a `d` — para que un `momento`
    arbitrario del cliente caiga en un día con datos del mapa."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return min(DIAS_CURADOS, key=lambda s: abs((date.fromisoformat(s) - d).days))
