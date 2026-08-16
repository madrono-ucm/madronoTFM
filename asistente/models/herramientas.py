"""Modelos de datos que devolverían las `tools` del agente MCP (esqueleto).

Ninguna de estas clases se construye todavía: las `tools` de
`asistente/mcp_agent/tools.py` levantan `NotImplementedError` en vez de
devolver una instancia. Se definen aquí de todas formas porque son parte del
contrato de cada `tool` (su firma declara este tipo de retorno) y porque el
SDK de MCP las usa para generar el `output_schema` que un cliente MCP vería
(comprobado en esta tarea instanciando `MCPServer` con estas `tools`
registradas, ver `asistente/tests/test_mcp_tools.py`).

Cada campo `fuente_dataset` es, a propósito, un `str` libre y no un `Enum`
cerrado sobre los datasets de `ingesta/capturas/`: cuando una `tool` tenga
lógica real, es más probable que combine varios datasets (p.ej.
`opciones_movilidad` cruzando `trafico`, `transporte_publico_emt` y
`bicimad`) que se apoye en uno solo, y fijar aquí un `Enum` obligaría a
listar de antemano una combinación que todavía no se conoce.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AfluenciaPrevista(BaseModel):
    """Nivel de afluencia previsto en un lugar y momento concretos."""

    lugar: str
    momento: datetime
    nivel_ocupacion: str
    fuente_dataset: str


class CalidadAireZona(BaseModel):
    """Calidad del aire prevista o medida en una zona y momento concretos."""

    zona: str
    momento: datetime
    indice_calidad: str
    contaminante_principal: str | None = None
    fuente_dataset: str


class OpcionMovilidad(BaseModel):
    """Una alternativa de desplazamiento entre dos puntos."""

    modo: str
    duracion_estimada_min: float | None = None
    incidencias: list[str] = Field(default_factory=list)
    fuente_dataset: str


class DisponibilidadAparcamiento(BaseModel):
    """Plazas de aparcamiento libres estimadas en una zona."""

    zona: str
    plazas_libres: int | None = None
    plazas_totales: int | None = None
    fuente_dataset: str


class EventoCercano(BaseModel):
    """Un evento o recinto con actividad cerca de un lugar dado."""

    nombre: str
    lugar: str
    distancia_m: float
    inicio: datetime
    fuente_dataset: str
