"""`tools` del agente MCP de Madroño (tarea 044; primera con lógica real,
`calidad_aire`, tarea 079).

La memoria del TFM (apartado 6.7) describe el asistente respondiendo
preguntas de movilidad y vida urbana apoyándose en varias señales: afluencia
prevista, calidad del aire, opciones de movilidad, disponibilidad de
aparcamiento y eventos cercanos. Estas cinco funciones anticipan esa
interfaz (firma y docstring, registradas como `tools` MCP en
`asistente/mcp_agent/server.py`) a partir de lo que `ingesta/` ya captura
hoy. Con Gold en producción (doc/041 y siguientes) y Athena fiable (tareas
041-068), `calidad_aire` ya lee datos reales (ver su docstring); las otras
cuatro siguen levantando `NotImplementedError` -- son tareas de seguimiento
separadas, cada una bloqueada por piezas distintas (`opciones_movilidad`
cruza 3 datasets; `afluencia_prevista` necesita `GOOGLE_MAPS_API_KEY`, no
disponible en este entorno; `eventos_cercanos` y
`disponibilidad_aparcamiento` no se han abordado por alcance, no por
bloqueo técnico).

Las funciones son planas (sin decorador `@mcp.tool()` aquí) a propósito, en
dos capas separadas:

- Este módulo declara la interfaz y es trivial de testear de forma aislada
  (firma, tipos, docstring) sin necesidad de una instancia de `MCPServer`.
- `asistente/mcp_agent/server.py` las registra sobre la instancia real vía
  `MCPServer.add_tool()`.
"""

from __future__ import annotations

from datetime import datetime

from asistente.athena import GOLD_DATABASE, run_athena_query, sql_literal
from asistente.models.herramientas import (
    AfluenciaPrevista,
    CalidadAireZona,
    DisponibilidadAparcamiento,
    EventoCercano,
    OpcionMovilidad,
)
from asistente.timeutils import MADRID_TZ, now_madrid

# Tabla Gold real, ya verificada con datos de producción en las tareas
# 049/066/068/069 (`gold.calidad_aire_por_estacion_contaminante_hora`,
# columnas: station_id/station_name/pollutant/pollutant_name/unit/hour/
# avg_value/max_value/min_value/samples_count/lat/lon, partición `date`).
_TABLA_CALIDAD_AIRE = "calidad_aire_por_estacion_contaminante_hora"
_FUENTE_CALIDAD_AIRE = f"gold.{_TABLA_CALIDAD_AIRE}"

# Límites de referencia (Real Decreto 102/2011 / Directiva 2008/50/CE, µg/m³)
# usados *solo* para elegir de forma simple qué contaminante destacar cuando
# una zona/hora reporta varios -- no es un cálculo del Índice de Calidad del
# Aire oficial (que combina más señales y periodos de promediado distintos
# por contaminante). NO2/SO2/O3 usan su límite/umbral horario oficial;
# PM10/PM2.5/CO no tienen límite horario oficial, así que se usa su límite
# diario/anual/8h como referencia aproximada -- deliberadamente simple, ver
# `asistente/README.md`.
_LIMITES_REFERENCIA_UGM3: dict[str, float] = {
    "NO2": 200.0,
    "SO2": 350.0,
    "O3": 180.0,
    "PM10": 50.0,
    "PM2.5": 25.0,
    "CO": 10_000.0,  # 10 mg/m³
}

_BANDAS_INDICE = (
    (0.5, "buena"),
    (1.0, "regular"),
    (1.5, "mala"),
)


def _clasificar_indice(ratio: float) -> str:
    for limite, etiqueta in _BANDAS_INDICE:
        if ratio < limite:
            return etiqueta
    return "muy mala"


def _calidad_aire_impl(
    zona: str, momento: datetime | None, *, athena_client=None
) -> CalidadAireZona:
    # Gold agrupa `date`/`hour` en hora de Madrid (misma zona que
    # ingesta.capturas.calidad_aire_madrid, ver aggregate.py). Un `momento`
    # aware en otra zona (p.ej. UTC) debe convertirse antes de leer
    # `.date()`/`.hour`, o se filtraría por la hora equivocada; uno naive se
    # asume ya en hora de Madrid (mismo criterio que el resto del proyecto).
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()
    fecha = instante.date().isoformat()
    zona_literal = sql_literal(zona.lower())

    sql = f"""
        SELECT station_id, station_name, pollutant, pollutant_name, unit,
               hour, avg_value, max_value, min_value, samples_count
        FROM {_TABLA_CALIDAD_AIRE}
        WHERE date = '{fecha}'
          AND (lower(station_name) LIKE '%{zona_literal}%'
               OR lower(station_id) LIKE '%{zona_literal}%')
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)

    if not filas:
        return CalidadAireZona(
            zona=zona,
            momento=instante,
            indice_calidad="sin_datos",
            fuente_dataset=_FUENTE_CALIDAD_AIRE,
        )

    if momento is not None:
        hora_objetivo = instante.hour
    else:
        hora_objetivo = max(fila["hour"] for fila in filas)
    filas_hora = [fila for fila in filas if fila["hour"] == hora_objetivo]

    if not filas_hora:
        return CalidadAireZona(
            zona=zona,
            momento=instante,
            indice_calidad="sin_datos",
            hora=hora_objetivo,
            fuente_dataset=_FUENTE_CALIDAD_AIRE,
        )

    # Varias estaciones pueden coincidir con `zona` (coincidencia de texto
    # sobre station_name/station_id, ver asistente/README.md) -- para cada
    # contaminante se toma la estación con mayor `avg_value`: criterio
    # conservador (el peor caso entre las estaciones que coinciden), simple
    # de explicar y suficiente para esta primera tool. Filas con
    # `avg_value=None` (sin ninguna muestra válida) se descartan: no hay
    # nada que comparar ni que mostrar como "peor caso".
    peor_por_contaminante: dict[str, dict] = {}
    for fila in filas_hora:
        valor = fila.get("avg_value")
        if valor is None:
            continue
        actual = peor_por_contaminante.get(fila["pollutant"])
        if actual is None or valor > actual["avg_value"]:
            peor_por_contaminante[fila["pollutant"]] = fila

    if not peor_por_contaminante:
        return CalidadAireZona(
            zona=zona,
            momento=instante,
            indice_calidad="sin_datos",
            hora=hora_objetivo,
            fuente_dataset=_FUENTE_CALIDAD_AIRE,
        )

    estaciones = sorted({fila["station_name"] or fila["station_id"] for fila in filas_hora})

    mejor_contaminante = None
    mejor_ratio = None
    for pollutant, fila in peor_por_contaminante.items():
        limite = _LIMITES_REFERENCIA_UGM3.get(pollutant)
        valor = fila.get("avg_value")
        if limite is None or valor is None:
            continue
        ratio = valor / limite
        if mejor_ratio is None or ratio > mejor_ratio:
            mejor_ratio = ratio
            mejor_contaminante = pollutant

    if mejor_contaminante is None:
        # Ninguno de los contaminantes presentes tiene límite de referencia
        # conocido (p.ej. NOx, TOL) -- último recurso: el de mayor avg_value
        # bruto, sin pretender que sea "peor" en términos comparables.
        mejor_contaminante, fila_elegida = max(
            peor_por_contaminante.items(), key=lambda item: item[1].get("avg_value") or 0
        )
        indice = "sin_clasificar"
    else:
        fila_elegida = peor_por_contaminante[mejor_contaminante]
        indice = _clasificar_indice(mejor_ratio)

    return CalidadAireZona(
        zona=zona,
        momento=instante,
        indice_calidad=indice,
        contaminante_principal=mejor_contaminante,
        valor=fila_elegida.get("avg_value"),
        unidad=fila_elegida.get("unit"),
        hora=hora_objetivo,
        estaciones_consultadas=estaciones,
        fuente_dataset=_FUENTE_CALIDAD_AIRE,
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
    """Calidad del aire medida en una zona de Madrid (tarea 079: primera
    `tool` con lógica real, ver `asistente/README.md`).

    Fuente: `gold.calidad_aire_por_estacion_contaminante_hora` (mediciones
    reales de `ingesta.capturas.calidad_aire_madrid`, tarea 006), consultada
    vía Athena (`asistente/athena.py`, mismo patrón que `grafo/extract.py`,
    tarea 069). **No usa `cams_calidad_aire_madrid`** (previsión Copernicus
    CAMS, tarea 019) -- fuera de alcance de esta tarea, que cubre solo la
    medición real.

    Simplificación deliberada de `zona`: Gold no tiene una dimensión de
    barrio/distrito (esa resolución espacial es el trabajo del grafo, tareas
    043/067-071). Aquí `zona` se resuelve por coincidencia de texto (case
    insensitive, `LIKE '%zona%'`) contra `station_name`/`station_id` de la
    propia tabla -- p.ej. "Ramón y Cajal", "Retiro" (si aparece en el nombre
    de una estación), no un barrio/distrito real. No implementa resolución
    por distrito/barrio.

    Si ninguna estación coincide (o no hay datos para la hora pedida), no
    lanza una excepción: devuelve `CalidadAireZona` con
    `indice_calidad="sin_datos"` y `contaminante_principal=None`.

    Si varias estaciones coinciden con `zona`, se agregan contaminante a
    contaminante tomando la estación con mayor `avg_value` (criterio
    conservador: el peor caso entre las que coinciden) -- ver
    `_calidad_aire_impl` para el detalle completo, incluida la elección de
    `contaminante_principal`/`indice_calidad`.

    Args:
        zona: Nombre o identificador (parcial) de una estación de la red de
            calidad del aire de Madrid a consultar.
        momento: Instante para el que se quiere el dato (se usa su fecha y
            hora exacta). Si es `None`, se asume el instante actual (hora de
            Madrid) y se usa la última hora con datos disponibles ese día.
    """
    return _calidad_aire_impl(zona, momento)


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
