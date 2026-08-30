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

from asistente.models.respuesta import RespuestaPrevision


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


class EstacionRuidoCercana(BaseModel):
    """Una estación de ruido encontrada cerca de un `:Lugar` del grafo
    (tarea 089), con su nivel más reciente de Gold. Mismo criterio que
    `EstacionTraficoCercana`: el campo de Gold es opcional porque el grafo
    puede encontrar una estación sin que Gold tenga fila para la fecha
    consultada."""

    station_id: str
    distancia_m: float
    avg_laeq_db: float | None = None


class ParadaBicimadCercana(BaseModel):
    """Una estación BiciMAD encontrada cerca de un `:Lugar` del grafo
    (tarea 089), con su ocupación más reciente de Gold."""

    station_id: str
    distancia_m: float
    avg_bikes_available: float | None = None
    avg_docks_available: float | None = None
    avg_occupancy_ratio: float | None = None


class EstacionCalidadAireCercana(BaseModel):
    """Una estación de calidad del aire encontrada cerca de un `:Lugar` del
    grafo (tarea 089) -- señal más débil/indirecta de `afluencia_estimada`,
    no contribuye a `nivel_estimado`, solo se lista para trazabilidad (ver
    el docstring de `asistente.mcp_agent.tools.afluencia_estimada`)."""

    station_id: str
    distancia_m: float
    contaminante_principal: str | None = None
    valor: float | None = None


class AfluenciaEstimada(BaseModel):
    """Actividad urbana estimada cerca de un lugar de Madrid (tarea 089,
    sustituye a `afluencia_prevista`/tarea 044): combina tráfico, ruido,
    BiciMAD y calidad del aire vía el grafo urbano en Neo4j (`:Lugar`
    -[:PROXIMO_A]- varios tipos de nodo) con sus respectivas tablas Gold --
    ver `asistente/mcp_agent/tools.py::afluencia_estimada` para el criterio
    exacto de resolución y agregación.

    **No es un conteo de personas.** El diseño original (tarea 086) usaba
    `aforos_peatones_bicicletas` (conteos reales de peatones/bicicletas)
    como señal primaria, pero esa fuente resultó estar descontinuada desde
    2024-06-30 (ver `doc/087-...md`) -- ninguna de las cuatro señales de
    aquí mide peatones directamente, son un proxy de actividad urbana
    general (tráfico/ruido/movilidad activa).

    `nivel_estimado` (`"bajo"`/`"medio"`/`"alto"`/`"sin_datos"`) combina las
    etiquetas simplificadas de tráfico/ruido/BiciMAD (no calidad del aire,
    señal deliberadamente excluida del cálculo) -- etiqueta simplificada, no
    una métrica oficial, misma filosofía que `TraficoCercano.resumen`."""

    lugar: str
    momento: datetime
    radio_m: float
    nivel_estimado: str
    hora: int | None = None
    trafico: list[EstacionTraficoCercana] = Field(default_factory=list)
    ruido: list[EstacionRuidoCercana] = Field(default_factory=list)
    bicimad: list[ParadaBicimadCercana] = Field(default_factory=list)
    calidad_aire: list[EstacionCalidadAireCercana] = Field(default_factory=list)
    fuente_grafo: str
    fuentes_gold: list[str] = Field(default_factory=list)


class OpcionMovilidad(BaseModel):
    """Una alternativa de desplazamiento entre dos puntos."""

    modo: str
    duracion_estimada_min: float | None = None
    incidencias: list[str] = Field(default_factory=list)
    fuente_dataset: str


class DisponibilidadAparcamiento(BaseModel):
    """Plazas de aparcamiento libres estimadas en una zona y momento
    concretos (tarea 090: implementación real, ver
    `asistente/mcp_agent/tools.py::disponibilidad_aparcamiento`).

    A diferencia de `CalidadAireZona` (que toma el peor caso entre varias
    estaciones coincidentes), varios aparcamientos que coinciden con `zona`
    representan capacidad real distinta y aditiva -- `plazas_libres`/
    `plazas_totales` son la **suma** entre los aparcamientos de
    `aparcamientos_consultados`, no el de un único aparcamiento "peor caso".
    """

    zona: str
    momento: datetime
    plazas_libres: int | None = None
    plazas_totales: int | None = None
    hora: int | None = None
    aparcamientos_consultados: list[str] = Field(default_factory=list)
    fuente_dataset: str


class EventoCercano(BaseModel):
    """Un evento o recinto con actividad cerca de un lugar dado."""

    nombre: str
    lugar: str
    distancia_m: float
    inicio: datetime
    fuente_dataset: str


class CalidadAirePrevista(RespuestaPrevision):
    """Previsión de calidad del aire para una estación y horizonte (tarea
    `ML_09`): la sirve `asistente.mcp_agent.tools.calidad_aire_prevista`
    corriendo el modelo ONNX de `ML_07` (LightGBM multi-horizonte de `ML_03`,
    exportado a ONNX) sobre las features construidas a partir de las últimas
    24 h de `gold.calidad_aire_por_estacion_contaminante_hora`.

    El envoltorio común (`momento`/`momento_objetivo`/`valor_previsto`/
    `disponible`/`motivo`/`modelo`/`data_completeness`/… — ver
    `RespuestaPrevision`) más los campos propios del dominio: `zona`
    consultada, `estacion` fijada (peor caso) y `contaminante`.
    `valor_previsto` es µg/m³ del `contaminante` a `horizonte_horas`;
    `nivel_previsto` reusa el índice simplificado de `CalidadAireZona`.
    """

    zona: str
    estacion: str | None = None
    contaminante: str | None = None


class TraficoPrevista(RespuestaPrevision):
    """Previsión de congestión de tráfico para un punto de medida y horizonte
    (`FIL_13`): la sirve `asistente.mcp_agent.tools.trafico_prevista`
    corriendo el modelo ONNX de `ML_07` (`madrono-trafico-h<H>@champion`,
    LightGBM de `ML_03`, exportado) sobre el mismo vector de 19 features que
    `calidad_aire_prevista` (`modelado/features/panel.py` es agnóstico del
    target), construido de las últimas 24 h de
    `gold.trafico_por_punto_hora`.

    El envoltorio común (ver `RespuestaPrevision`) más los campos del
    dominio: `lugar` consultado, `punto_id` fijado (peor caso) y
    `fuente_grafo` (Neo4j resolvió el lugar → puntos de tráfico).
    `valor_previsto` es `avg_service_level` (0=fluido .. 6=cortado, escala de
    la API de tráfico de Madrid); `nivel_previsto` reusa las tres bandas de
    `trafico_cercano` (`fluido`/`denso`/`congestionado`).
    """

    lugar: str
    punto_id: str | None = None
    unidad: str | None = "avg_service_level"
    fuente_grafo: str | None = None
