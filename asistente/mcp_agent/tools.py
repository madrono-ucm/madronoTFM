"""Esqueleto de las `tools` del agente MCP de Madroño (tarea 044).

La memoria del TFM (apartado 6.7) describe el asistente respondiendo
preguntas de movilidad y vida urbana apoyándose en varias señales: afluencia
prevista, calidad del aire, opciones de movilidad, disponibilidad de
aparcamiento y eventos cercanos. Estas cinco funciones anticipan esa
interfaz (firma y docstring, registradas como `tools` MCP en
`asistente/mcp_agent/server.py`) a partir de lo que `ingesta/` ya captura
hoy, pero **ninguna tiene lógica real todavía**: todas levantan
`NotImplementedError`.

Por qué ahora mismo no hay más que eso: cada una necesita leer de la capa
Gold del lakehouse (agregados limpios y validados, ver
`procesamiento/README.md`, doc/041), y hoy Gold solo existe como piloto de
un único dataset (tráfico) sin desplegar en AWS. Implementar estas `tools`
de verdad antes de que exista Gold para el resto de fuentes produciría
lógica de negocio sin datos que consultar, o forzaría a leer directamente de
Bronze/Silver (saltándose la puerta de calidad y la agregación que Gold ya
resuelve) — ninguna de las dos envejece bien cuando Gold sí exista.

Las funciones son planas (sin decorador `@mcp.tool()` aquí) a propósito, en
dos capas separadas:

- Este módulo declara la interfaz y es trivial de testear de forma aislada
  (firma, tipos, docstring) sin necesidad de una instancia de `MCPServer`.
- `asistente/mcp_agent/server.py` las registra sobre la instancia real vía
  `MCPServer.add_tool()`.
"""

from __future__ import annotations

from datetime import datetime

from asistente.models.herramientas import (
    AfluenciaPrevista,
    CalidadAireZona,
    DisponibilidadAparcamiento,
    EventoCercano,
    OpcionMovilidad,
)


def afluencia_prevista(lugar: str, momento: datetime | None = None) -> AfluenciaPrevista:
    """Nivel de afluencia previsto en un lugar de Madrid.

    Fuente futura: `ingesta.capturas.afluencia_lugares_madrid` (tarea 012,
    scraping de "popular times" de Google) agregado en Gold por punto/hora.

    Args:
        lugar: Nombre o identificador del lugar/POI a consultar
            (p.ej. "Puerta del Sol", o el `place_id` usado por el productor).
        momento: Instante para el que se quiere la previsión. Si es `None`,
            se asume el instante actual.
    """
    raise NotImplementedError(
        "afluencia_prevista: pendiente de Gold real para "
        "afluencia_lugares_madrid (ver doc/041 y el docstring de este módulo)"
    )


def calidad_aire(zona: str, momento: datetime | None = None) -> CalidadAireZona:
    """Calidad del aire medida o prevista en una zona de Madrid.

    Fuente futura: `ingesta.capturas.calidad_aire_madrid` (mediciones reales,
    tarea 006) para el pasado/presente, y
    `ingesta.capturas.cams_calidad_aire_madrid` (previsión Copernicus CAMS,
    tarea 019) para el futuro cercano, agregadas en Gold por zona/hora.

    Args:
        zona: Barrio, distrito o estación de la red de calidad del aire a
            consultar.
        momento: Instante para el que se quiere el dato. Si es `None`, se
            asume el instante actual (medición real, no previsión).
    """
    raise NotImplementedError(
        "calidad_aire: pendiente de Gold real para calidad_aire_madrid / "
        "cams_calidad_aire_madrid (ver doc/041 y el docstring de este módulo)"
    )


def opciones_movilidad(
    origen: str, destino: str, momento: datetime | None = None
) -> list[OpcionMovilidad]:
    """Alternativas de desplazamiento entre dos puntos de Madrid.

    Fuente futura: combina `ingesta.capturas.trafico_madrid` (tarea 002),
    `ingesta.capturas.transporte_publico_madrid` (EMT, tarea 003) y
    `ingesta.capturas.bicimad` (tarea 004) agregados en Gold, cruzando
    origen/destino contra la red viaria/de transporte
    (`ingesta.capturas.callejero_madrid`, `crtm_red_transporte_madrid`).

    Args:
        origen: Punto de partida (dirección, lugar o coordenadas).
        destino: Punto de llegada (dirección, lugar o coordenadas).
        momento: Instante del desplazamiento. Si es `None`, se asume el
            instante actual.
    """
    raise NotImplementedError(
        "opciones_movilidad: pendiente de Gold real para tráfico/EMT/BiciMAD "
        "(ver doc/041 y el docstring de este módulo)"
    )


def disponibilidad_aparcamiento(zona: str) -> DisponibilidadAparcamiento:
    """Plazas de aparcamiento libres estimadas en una zona de Madrid.

    Fuente futura: `ingesta.capturas.aparcamientos_madrid` (tarea 005)
    agregado en Gold por zona/hora.

    Args:
        zona: Barrio, distrito o aparcamiento concreto a consultar.
    """
    raise NotImplementedError(
        "disponibilidad_aparcamiento: pendiente de Gold real para "
        "aparcamientos_madrid (ver doc/041 y el docstring de este módulo)"
    )


def eventos_cercanos(
    lugar: str, radio_m: float = 500.0, momento: datetime | None = None
) -> list[EventoCercano]:
    """Eventos o recintos con actividad cerca de un lugar de Madrid.

    Fuente futura: combina `ingesta.capturas.agenda_eventos_madrid` (tarea
    017) y `ingesta.capturas.agenda_recintos_madrid` agregados en Gold,
    filtrados por proximidad geográfica al `lugar` dado.

    Args:
        lugar: Lugar de referencia (dirección, lugar o coordenadas).
        radio_m: Radio de búsqueda en metros alrededor de `lugar`.
        momento: Instante para el que se buscan eventos activos/próximos. Si
            es `None`, se asume el instante actual.
    """
    raise NotImplementedError(
        "eventos_cercanos: pendiente de Gold real para agenda_eventos_madrid "
        "/ agenda_recintos_madrid (ver doc/041 y el docstring de este módulo)"
    )
