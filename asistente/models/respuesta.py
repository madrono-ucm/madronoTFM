"""Esquema de la respuesta del asistente (memoria del TFM, apartado 6.7).

La memoria describe el asistente respondiendo preguntas del tipo «¿voy al
centro a las nueve de la noche del viernes?» con tres elementos: un
veredicto, un nivel de fiabilidad y una explicación trazable a los datos que
la sustentan. `RespuestaAsistente` es ese contrato, como modelo Pydantic
reutilizable por cualquier router/tool que lo necesite en el futuro — hoy no
lo construye nadie todavía (no hay lógica real, ver
`asistente/mcp_agent/tools.py`), pero el esquema en sí no depende de que
exista esa lógica.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from asistente.timeutils import now_madrid


class Veredicto(str, Enum):
    """Resultado de alto nivel de la pregunta planteada al asistente."""

    FAVORABLE = "favorable"
    DESFAVORABLE = "desfavorable"
    CON_PRECAUCION = "con_precaucion"


class NivelFiabilidad(str, Enum):
    """Cuánto se puede confiar en el veredicto, dados los datos disponibles.

    No es una medida de la calidad del dato en sí (eso ya lo filtra la
    puerta de calidad de `procesamiento/`, ver doc/041), sino de cuánto
    cubren los datos disponibles la pregunta concreta: por ejemplo, una
    previsión a varios días vista con pocas fuentes coincidentes debería
    resultar en `BAJA`, aunque cada dato individual sea válido.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class FuenteConsultada(BaseModel):
    """Un dato concreto citado en la explicación, trazable a su origen."""

    dataset: str
    resumen: str
    consultado_en: datetime | None = None


class RespuestaAsistente(BaseModel):
    """Respuesta completa del asistente a una pregunta en lenguaje natural."""

    pregunta: str
    veredicto: Veredicto
    fiabilidad: NivelFiabilidad
    explicacion: str
    fuentes: list[FuenteConsultada] = Field(default_factory=list)
    generado_en: datetime = Field(default_factory=now_madrid)
