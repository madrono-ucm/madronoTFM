"""Modelos de datos que devuelven las `tools` del agente MCP.

`CalidadAireZona` (tarea 079) y `TraficoCercano` (tarea 081, primera `tool`
que cruza datasets vía el grafo Neo4j -- ver
`asistente/mcp_agent/tools.py::trafico_cercano`) ya se construyen de verdad.
El resto de clases siguen sin construirse: esas `tools` levantan
`NotImplementedError` en vez de devolver una instancia. Se definen aquí de
todas formas porque son parte del contrato de cada `tool` (su firma declara
este tipo de retorno) y porque el SDK de MCP las usa para generar el
`output_schema` que un cliente MCP vería (comprobado en esta tarea
instanciando `MCPServer` con estas `tools` registradas, ver
`asistente/tests/test_mcp_tools.py`).

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
    """Calidad del aire medida en una zona y momento concretos (tarea 079,
    primera `tool` con lógica real: ver `asistente/mcp_agent/tools.py`).

    `indice_calidad` es una etiqueta simplificada (`"buena"`/`"regular"`/
    `"mala"`/`"muy mala"`/`"sin_clasificar"`/`"sin_datos"`), no el Índice de
    Calidad del Aire oficial (que combina más señales y periodos de
    promediado distintos por contaminante) -- ver el docstring de
    `calidad_aire()` para el criterio exacto. `valor`/`unidad`/`hora` son el
    dato bruto de Gold para `contaminante_principal`, y
    `estaciones_consultadas` lista todas las estaciones que coincidieron con
    `zona`, para que la respuesta sea trazable incluso cuando se agregan
    varias.
    """

    zona: str
    momento: datetime
    indice_calidad: str
    contaminante_principal: str | None = None
    valor: float | None = None
    unidad: str | None = None
    hora: int | None = None
    estaciones_consultadas: list[str] = Field(default_factory=list)
    fuente_dataset: str


class EstacionTraficoCercana(BaseModel):
    """Una estación de medida de tráfico encontrada cerca de un `:Lugar` del
    grafo (tarea 081), con su dato más reciente de Gold. Los campos de Gold
    son opcionales porque el grafo puede encontrar una estación dentro del
    radio pedido sin que Gold tenga ninguna fila para la fecha/hora
    consultada (sensor sin lecturas esa hora) -- en ese caso se lista la
    estación (la proximidad sí es un dato real y trazable) con sus valores de
    tráfico en `None`, en vez de omitirla en silencio."""

    point_id: str
    distancia_m: float
    avg_intensity_vph: float | None = None
    avg_occupancy_ratio: float | None = None
    avg_service_level: float | None = None


class TraficoCercano(BaseModel):
    """Estado del tráfico cerca de un lugar de Madrid (tarea 081): cruza el
    grafo urbano en Neo4j (`:Lugar` -[:PROXIMO_A]- `:EstacionMedida {tipo:
    'trafico'}`, tarea 070) con `gold.trafico_por_punto_hora` (tarea 041) --
    ver `asistente/mcp_agent/tools.py::trafico_cercano` para el criterio
    exacto de resolución y agregación.

    `resumen` es una etiqueta simplificada (`"fluido"`/`"denso"`/
    `"congestionado"`/`"sin_datos"`), no un cálculo oficial -- misma
    filosofía que `CalidadAireZona.indice_calidad`."""

    lugar: str
    momento: datetime
    radio_m: float
    resumen: str
    hora: int | None = None
    estaciones: list[EstacionTraficoCercana] = Field(default_factory=list)
    fuente_grafo: str
    fuente_gold: str


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
