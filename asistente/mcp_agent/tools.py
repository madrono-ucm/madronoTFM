"""`tools` del agente MCP de Madroño (tarea 044; primera con lógica real,
`calidad_aire`, tarea 079).

La memoria del TFM (apartado 6.7) describe el asistente respondiendo
preguntas de movilidad y vida urbana apoyándose en varias señales: afluencia
estimada, calidad del aire, opciones de movilidad, disponibilidad de
aparcamiento y eventos cercanos. Estas cinco funciones anticipan esa
interfaz (firma y docstring, registradas como `tools` MCP en
`asistente/mcp_agent/server.py`) a partir de lo que `ingesta/` ya captura
hoy. Las seis ya leen datos reales: `calidad_aire` (tarea 079),
`trafico_cercano` (tarea 081), `afluencia_estimada` (tarea 089, sustituye a
la `afluencia_prevista` original -- ver su docstring), `disponibilidad_
aparcamiento` (tarea 090), `eventos_cercanos` (tarea 095) y
`opciones_movilidad` (tarea 096, simplificación deliberada -- sin routing
real, ver su docstring).

Las funciones son planas (sin decorador `@mcp.tool()` aquí) a propósito, en
dos capas separadas:

- Este módulo declara la interfaz y es trivial de testear de forma aislada
  (firma, tipos, docstring) sin necesidad de una instancia de `MCPServer`.
- `asistente/mcp_agent/server.py` las registra sobre la instancia real vía
  `MCPServer.add_tool()`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from asistente.athena import GOLD_DATABASE, SILVER_DATABASE, run_athena_query, sql_literal
from asistente.models.herramientas import (
    AfluenciaEstimada,
    CalidadAirePrevista,
    CalidadAireZona,
    DisponibilidadAparcamiento,
    EstacionCalidadAireCercana,
    EstacionRuidoCercana,
    EstacionTraficoCercana,
    EventoCercano,
    OpcionMovilidad,
    ParadaBicimadCercana,
    TraficoCercano,
    TraficoPrevista,
)
from asistente.neo4j_client import (
    lugares_proximos_a_estaciones_calidad_aire_query,
    lugares_proximos_a_estaciones_ruido_query,
    lugares_proximos_a_estaciones_trafico_query,
    lugares_proximos_a_paradas_bicimad_query,
    lugares_proximos_a_paradas_emt_query,
    resolver_lugar_query,
    run_neo4j_query,
)
from asistente import prevision
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


# Tabla Gold real (tarea 090 -- verificado en vivo con Athena, aparcamientos
# ya no tenía el bug de "0 filas" de doc/052, ver doc/090). Columnas:
# parking_id, name, hour, samples_count, first_measured_at, last_measured_at,
# avg_free_spaces, avg_occupancy_ratio, total_spaces, lat, lon, partición
# date.
_TABLA_APARCAMIENTOS = "aparcamientos_por_parking_hora"
_FUENTE_APARCAMIENTOS = f"gold.{_TABLA_APARCAMIENTOS}"


def _disponibilidad_aparcamiento_impl(
    zona: str, momento: datetime | None, *, athena_client=None
) -> DisponibilidadAparcamiento:
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()
    fecha = instante.date().isoformat()
    zona_literal = sql_literal(zona.lower())

    sql = f"""
        SELECT parking_id, name, hour, avg_free_spaces, avg_occupancy_ratio, total_spaces, samples_count
        FROM {_TABLA_APARCAMIENTOS}
        WHERE date = '{fecha}'
          AND (lower(name) LIKE '%{zona_literal}%' OR lower(parking_id) LIKE '%{zona_literal}%')
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)

    if not filas:
        return DisponibilidadAparcamiento(zona=zona, momento=instante, fuente_dataset=_FUENTE_APARCAMIENTOS)

    if momento is not None:
        hora_objetivo = instante.hour
    else:
        hora_objetivo = max(fila["hour"] for fila in filas)
    filas_hora = [fila for fila in filas if fila["hour"] == hora_objetivo]

    if not filas_hora:
        return DisponibilidadAparcamiento(
            zona=zona, momento=instante, hora=hora_objetivo, fuente_dataset=_FUENTE_APARCAMIENTOS
        )

    # A diferencia de `_calidad_aire_impl` (peor caso entre estaciones que
    # coinciden), varios aparcamientos que coinciden con `zona` representan
    # capacidad real distinta y aditiva -- se suman, no se toma un único
    # "peor caso". Filas con `avg_free_spaces`/`total_spaces=None` (sin
    # ninguna muestra válida esa hora) se excluyen de la suma en vez de
    # tratarse como 0 plazas, que subestimaría la capacidad real.
    aparcamientos = sorted({fila["name"] or fila["parking_id"] for fila in filas_hora})
    libres = [fila["avg_free_spaces"] for fila in filas_hora if fila.get("avg_free_spaces") is not None]
    totales = [fila["total_spaces"] for fila in filas_hora if fila.get("total_spaces") is not None]

    return DisponibilidadAparcamiento(
        zona=zona,
        momento=instante,
        hora=hora_objetivo,
        plazas_libres=round(sum(libres)) if libres else None,
        plazas_totales=sum(totales) if totales else None,
        aparcamientos_consultados=aparcamientos,
        fuente_dataset=_FUENTE_APARCAMIENTOS,
    )


# Tabla Gold real, la más madura del proyecto (piloto original, tarea 041,
# ya verificada en las tareas 049/066/068/069). Columnas: point_id, subarea,
# hour, avg_intensity_vph, max/min_intensity_vph, avg_occupancy_ratio,
# avg_load_ratio, avg_intensity_ratio, avg_service_level, lat, lon,
# samples_count, partición date.
_TABLA_TRAFICO = "trafico_por_punto_hora"
_FUENTE_TRAFICO = f"gold.{_TABLA_TRAFICO}"
_FUENTE_GRAFO_TRAFICO_CERCANO = "neo4j: (:Lugar)-[:PROXIMO_A]-(:EstacionMedida {tipo: 'trafico'})"

# `avg_service_level` reproduce el campo real "nivelServicio" de la API de
# tráfico de Madrid (0 = fluido .. 6 = cortado, ver
# `ingesta/capturas/trafico_madrid.py` y `MAX_PLAUSIBLE_SERVICE_LEVEL` en
# `procesamiento/silver_gold/trafico/transform.py`). Los umbrales de abajo
# son una simplificación deliberada para tres etiquetas, no la escala
# oficial completa -- mismo criterio que `_LIMITES_REFERENCIA_UGM3` con
# `calidad_aire`: un número simple con su limitación documentada.
_UMBRALES_SERVICE_LEVEL = ((1.5, "fluido"), (3.5, "denso"))
# Fallback cuando ninguna estación encontrada trae `avg_service_level` (pero
# sí `avg_occupancy_ratio`, 0-1): mismo criterio de tres bandas sobre una
# escala distinta.
_UMBRALES_OCCUPANCY_RATIO = ((0.3, "fluido"), (0.6, "denso"))


def _clasificar_trafico(valor: float, umbrales: "tuple[tuple[float, str], ...]") -> str:
    for limite, etiqueta in umbrales:
        if valor < limite:
            return etiqueta
    return "congestionado"


def _trafico_cercano_impl(
    lugar: str,
    radio_m: float,
    momento: datetime | None,
    *,
    neo4j_driver=None,
    athena_client=None,
) -> TraficoCercano:
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()

    def _sin_datos() -> TraficoCercano:
        return TraficoCercano(
            lugar=lugar,
            momento=instante,
            radio_m=radio_m,
            resumen="sin_datos",
            fuente_grafo=_FUENTE_GRAFO_TRAFICO_CERCANO,
            fuente_gold=_FUENTE_TRAFICO,
        )

    query, params = lugares_proximos_a_estaciones_trafico_query(lugar, radio_m)
    filas_grafo = run_neo4j_query(query, params, driver=neo4j_driver)
    if not filas_grafo:
        return _sin_datos()

    # Varios `:Lugar` pueden coincidir con `lugar` (coincidencia de texto,
    # igual que `calidad_aire` con `zona`) y una misma estación puede
    # aparecer cerca de más de uno -- se agregan todas por `point_id`,
    # quedándose con la distancia mínima real cuando se repite.
    distancia_por_point_id: dict[str, float] = {}
    for fila in filas_grafo:
        estacion_id = fila.get("estacion_id") or ""
        point_id = estacion_id.split(":", 1)[1] if ":" in estacion_id else None
        if not point_id:
            continue
        actual = distancia_por_point_id.get(point_id)
        if actual is None or fila["distancia_m"] < actual:
            distancia_por_point_id[point_id] = fila["distancia_m"]

    if not distancia_por_point_id:
        return _sin_datos()

    fecha = instante.date().isoformat()
    ids_literal = ", ".join(f"'{sql_literal(pid)}'" for pid in sorted(distancia_por_point_id))
    sql = f"""
        SELECT point_id, hour, avg_intensity_vph, avg_occupancy_ratio,
               avg_load_ratio, avg_intensity_ratio, avg_service_level
        FROM {_TABLA_TRAFICO}
        WHERE date = '{fecha}'
          AND point_id IN ({ids_literal})
    """
    filas_gold = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)

    if momento is not None:
        hora_objetivo = instante.hour
    elif filas_gold:
        hora_objetivo = max(fila["hour"] for fila in filas_gold)
    else:
        hora_objetivo = None

    filas_hora = [fila for fila in filas_gold if fila["hour"] == hora_objetivo] if hora_objetivo is not None else []
    gold_por_point_id = {fila["point_id"]: fila for fila in filas_hora}

    estaciones = [
        EstacionTraficoCercana(
            point_id=point_id,
            distancia_m=distancia_por_point_id[point_id],
            avg_intensity_vph=(gold_por_point_id.get(point_id) or {}).get("avg_intensity_vph"),
            avg_occupancy_ratio=(gold_por_point_id.get(point_id) or {}).get("avg_occupancy_ratio"),
            avg_service_level=(gold_por_point_id.get(point_id) or {}).get("avg_service_level"),
        )
        for point_id in sorted(distancia_por_point_id, key=lambda pid: distancia_por_point_id[pid])
    ]

    niveles_servicio = [e.avg_service_level for e in estaciones if e.avg_service_level is not None]
    if niveles_servicio:
        resumen = _clasificar_trafico(sum(niveles_servicio) / len(niveles_servicio), _UMBRALES_SERVICE_LEVEL)
    else:
        ocupaciones = [e.avg_occupancy_ratio for e in estaciones if e.avg_occupancy_ratio is not None]
        if ocupaciones:
            resumen = _clasificar_trafico(sum(ocupaciones) / len(ocupaciones), _UMBRALES_OCCUPANCY_RATIO)
        else:
            resumen = "sin_datos"

    return TraficoCercano(
        lugar=lugar,
        momento=instante,
        radio_m=radio_m,
        resumen=resumen,
        hora=hora_objetivo,
        estaciones=estaciones,
        fuente_grafo=_FUENTE_GRAFO_TRAFICO_CERCANO,
        fuente_gold=_FUENTE_TRAFICO,
    )


# Tablas Gold reales de las tres señales secundarias/terciarias de
# `afluencia_estimada` (tarea 089 -- señal primaria, tráfico, reutiliza
# `_TABLA_TRAFICO` ya definida más abajo en este módulo).
_TABLA_RUIDO = "ruido_por_estacion_periodo_fecha"
_FUENTE_RUIDO = f"gold.{_TABLA_RUIDO}"
_TABLA_BICIMAD = "bicimad_por_estacion_hora"
_FUENTE_BICIMAD = f"gold.{_TABLA_BICIMAD}"
_FUENTE_GRAFO_AFLUENCIA = (
    "neo4j: (:Lugar)-[:PROXIMO_A]-(:EstacionMedida {tipo: 'trafico'|'ruido'|'calidad_aire'}"
    "|:ParadaTransporte {tipo: 'bicimad'})"
)

# `avg_laeq_db` (nivel medio de ruido, dB) -- sin escala oficial de "cuánta
# gente hay" (es contaminación acústica, no aforo), bandas de referencia
# ambiental aproximadas (guía de ruido ambiental de la UE/OMS: <55dB tramo
# bajo, 55-70dB tramo medio, >70dB tramo alto) -- mismo criterio de
# simplificación deliberada que `_UMBRALES_SERVICE_LEVEL`.
_UMBRALES_RUIDO_DB = ((55.0, "bajo"), (70.0, "medio"))
# `avg_occupancy_ratio` de BiciMAD (0-1): mismas tres bandas que
# `_UMBRALES_OCCUPANCY_RATIO` de tráfico -- se asume la misma dirección
# (ratio más alto = estación más activa/usada = más actividad urbana
# alrededor), no verificado contra una definición oficial del campo.
_UMBRALES_BICIMAD_OCUPACION = ((0.3, "bajo"), (0.6, "medio"))

# NOTA (FIL_06): la fórmula de `nivel_estimado` está duplicada, byte a byte,
# en `procesamiento/silver_gold/afluencia_lugares/nivel.py`, que la usa el
# job por lotes que materializa la señal como Gold horario. Es la copia
# canónica; un cambio de fórmula debe reflejarse en ambas (o, mejor, esta
# función debería pasar a importar de allí -- pendiente, evita tocar este
# módulo ya testado en la misma pasada que lo introdujo).

# Traduce las etiquetas de las tres señales que sí alimentan `nivel_estimado`
# (tráfico/ruido/BiciMAD, no calidad del aire) a una severidad 0-2 común
# para poder combinarlas -- ver `afluencia_estimada`.
_SEVERIDAD_POR_ETIQUETA = {
    "fluido": 0, "bajo": 0,
    "denso": 1, "medio": 1,
    "congestionado": 2, "alto": 2,
}
_SEVERIDAD_A_NIVEL = ((0.75, "bajo"), (1.5, "medio"))


def _clasificar_severidad(valor: float, umbrales: "tuple[tuple[float, str], ...]") -> str:
    for limite, etiqueta in umbrales:
        if valor < limite:
            return etiqueta
    return "alto"


def _agregar_por_id(filas_grafo: "list[dict]", campo_id: str = "estacion_id") -> "dict[str, float]":
    """Agrega filas de una consulta `lugares_proximos_a_*_query` por el
    identificador real tras el prefijo `"<fuente>:"` del nodo, quedándose
    con la distancia mínima cuando el mismo nodo aparece más de una vez
    (varios `:Lugar` coincidentes) -- mismo criterio que
    `_trafico_cercano_impl`."""
    distancia_por_id: "dict[str, float]" = {}
    for fila in filas_grafo:
        estacion_id = fila.get(campo_id) or ""
        real_id = estacion_id.split(":", 1)[1] if ":" in estacion_id else None
        if not real_id:
            continue
        actual = distancia_por_id.get(real_id)
        if actual is None or fila["distancia_m"] < actual:
            distancia_por_id[real_id] = fila["distancia_m"]
    return distancia_por_id


def _afluencia_estimada_impl(
    lugar: str,
    radio_m: float,
    momento: datetime | None,
    *,
    neo4j_driver=None,
    athena_client=None,
) -> AfluenciaEstimada:
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()

    def _sin_datos() -> AfluenciaEstimada:
        return AfluenciaEstimada(
            lugar=lugar,
            momento=instante,
            radio_m=radio_m,
            nivel_estimado="sin_datos",
            fuente_grafo=_FUENTE_GRAFO_AFLUENCIA,
            fuentes_gold=[],
        )

    query_trafico, params_trafico = lugares_proximos_a_estaciones_trafico_query(lugar, radio_m)
    query_ruido, params_ruido = lugares_proximos_a_estaciones_ruido_query(lugar, radio_m)
    query_calidad, params_calidad = lugares_proximos_a_estaciones_calidad_aire_query(lugar, radio_m)
    query_bicimad, params_bicimad = lugares_proximos_a_paradas_bicimad_query(lugar, radio_m)

    dist_trafico = _agregar_por_id(run_neo4j_query(query_trafico, params_trafico, driver=neo4j_driver))
    dist_ruido = _agregar_por_id(run_neo4j_query(query_ruido, params_ruido, driver=neo4j_driver))
    dist_calidad = _agregar_por_id(run_neo4j_query(query_calidad, params_calidad, driver=neo4j_driver))
    dist_bicimad = _agregar_por_id(run_neo4j_query(query_bicimad, params_bicimad, driver=neo4j_driver))

    if not (dist_trafico or dist_ruido or dist_calidad or dist_bicimad):
        return _sin_datos()

    fecha = instante.date().isoformat()
    hora_objetivo = instante.hour if momento is not None else None
    fuentes_gold: "list[str]" = []

    # --- Tráfico (hora exacta u hora más reciente del día, igual que trafico_cercano) ---
    trafico: "list[EstacionTraficoCercana]" = []
    if dist_trafico:
        ids_literal = ", ".join(f"'{sql_literal(pid)}'" for pid in sorted(dist_trafico))
        sql = f"""
            SELECT point_id, hour, avg_intensity_vph, avg_occupancy_ratio, avg_service_level
            FROM {_TABLA_TRAFICO}
            WHERE date = '{fecha}' AND point_id IN ({ids_literal})
        """
        filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
        fuentes_gold.append(_FUENTE_TRAFICO)
        hora_trafico = hora_objetivo if hora_objetivo is not None else (max((f["hour"] for f in filas), default=None))
        gold_por_id = {f["point_id"]: f for f in filas if f["hour"] == hora_trafico}
        trafico = [
            EstacionTraficoCercana(
                point_id=pid,
                distancia_m=dist_trafico[pid],
                avg_intensity_vph=(gold_por_id.get(pid) or {}).get("avg_intensity_vph"),
                avg_occupancy_ratio=(gold_por_id.get(pid) or {}).get("avg_occupancy_ratio"),
                avg_service_level=(gold_por_id.get(pid) or {}).get("avg_service_level"),
            )
            for pid in sorted(dist_trafico, key=lambda p: dist_trafico[p])
        ]

    # --- Ruido: sin columna `hour` en Gold (partición solo por `date`,
    # `period` es D/N/T) -- se toma cualquier fila del día para cada
    # estación, sin filtrar por periodo (ver doc/089-...md si existe, o el
    # docstring de afluencia_estimada para el porqué de esta simplificación).
    ruido: "list[EstacionRuidoCercana]" = []
    if dist_ruido:
        ids_literal = ", ".join(f"'{sql_literal(sid)}'" for sid in sorted(dist_ruido))
        sql = f"""
            SELECT station_id, period, avg_laeq_db
            FROM {_TABLA_RUIDO}
            WHERE date = '{fecha}' AND station_id IN ({ids_literal})
        """
        filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
        fuentes_gold.append(_FUENTE_RUIDO)
        gold_por_id: "dict[str, dict]" = {}
        for f in filas:
            if f["station_id"] not in gold_por_id:
                gold_por_id[f["station_id"]] = f
        ruido = [
            EstacionRuidoCercana(
                station_id=sid,
                distancia_m=dist_ruido[sid],
                avg_laeq_db=(gold_por_id.get(sid) or {}).get("avg_laeq_db"),
            )
            for sid in sorted(dist_ruido, key=lambda s: dist_ruido[s])
        ]

    # --- BiciMAD (hora exacta u hora más reciente del día) ---
    bicimad: "list[ParadaBicimadCercana]" = []
    if dist_bicimad:
        ids_literal = ", ".join(f"'{sql_literal(sid)}'" for sid in sorted(dist_bicimad))
        sql = f"""
            SELECT station_id, hour, avg_bikes_available, avg_docks_available, avg_occupancy_ratio
            FROM {_TABLA_BICIMAD}
            WHERE date = '{fecha}' AND station_id IN ({ids_literal})
        """
        filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
        fuentes_gold.append(_FUENTE_BICIMAD)
        hora_bicimad = hora_objetivo if hora_objetivo is not None else (max((f["hour"] for f in filas), default=None))
        gold_por_id = {f["station_id"]: f for f in filas if f["hour"] == hora_bicimad}
        bicimad = [
            ParadaBicimadCercana(
                station_id=sid,
                distancia_m=dist_bicimad[sid],
                avg_bikes_available=(gold_por_id.get(sid) or {}).get("avg_bikes_available"),
                avg_docks_available=(gold_por_id.get(sid) or {}).get("avg_docks_available"),
                avg_occupancy_ratio=(gold_por_id.get(sid) or {}).get("avg_occupancy_ratio"),
            )
            for sid in sorted(dist_bicimad, key=lambda s: dist_bicimad[s])
        ]

    # --- Calidad del aire: señal de trazabilidad, no contribuye a nivel_estimado ---
    calidad_aire_lista: "list[EstacionCalidadAireCercana]" = []
    if dist_calidad:
        ids_literal = ", ".join(f"'{sql_literal(sid)}'" for sid in sorted(dist_calidad))
        sql = f"""
            SELECT station_id, pollutant, hour, avg_value
            FROM {_TABLA_CALIDAD_AIRE}
            WHERE date = '{fecha}' AND station_id IN ({ids_literal})
        """
        filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
        fuentes_gold.append(_FUENTE_CALIDAD_AIRE)
        hora_calidad = hora_objetivo if hora_objetivo is not None else (max((f["hour"] for f in filas), default=None))
        filas_hora = [f for f in filas if f["hour"] == hora_calidad]
        peor_por_id: "dict[str, dict]" = {}
        for f in filas_hora:
            valor = f.get("avg_value")
            if valor is None:
                continue
            actual = peor_por_id.get(f["station_id"])
            if actual is None or valor > actual["avg_value"]:
                peor_por_id[f["station_id"]] = f
        calidad_aire_lista = [
            EstacionCalidadAireCercana(
                station_id=sid,
                distancia_m=dist_calidad[sid],
                contaminante_principal=(peor_por_id.get(sid) or {}).get("pollutant"),
                valor=(peor_por_id.get(sid) or {}).get("avg_value"),
            )
            for sid in sorted(dist_calidad, key=lambda s: dist_calidad[s])
        ]

    # --- nivel_estimado: combina tráfico/ruido/BiciMAD (no calidad del aire) ---
    severidades: "list[int]" = []
    niveles_servicio = [e.avg_service_level for e in trafico if e.avg_service_level is not None]
    if niveles_servicio:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[_clasificar_trafico(sum(niveles_servicio) / len(niveles_servicio), _UMBRALES_SERVICE_LEVEL)])
    else:
        ocupaciones_trafico = [e.avg_occupancy_ratio for e in trafico if e.avg_occupancy_ratio is not None]
        if ocupaciones_trafico:
            severidades.append(_SEVERIDAD_POR_ETIQUETA[_clasificar_trafico(sum(ocupaciones_trafico) / len(ocupaciones_trafico), _UMBRALES_OCCUPANCY_RATIO)])

    niveles_ruido = [e.avg_laeq_db for e in ruido if e.avg_laeq_db is not None]
    if niveles_ruido:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[_clasificar_severidad(sum(niveles_ruido) / len(niveles_ruido), _UMBRALES_RUIDO_DB)])

    ocupaciones_bicimad = [e.avg_occupancy_ratio for e in bicimad if e.avg_occupancy_ratio is not None]
    if ocupaciones_bicimad:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[_clasificar_severidad(sum(ocupaciones_bicimad) / len(ocupaciones_bicimad), _UMBRALES_BICIMAD_OCUPACION)])

    if severidades:
        nivel_estimado = _clasificar_severidad(sum(severidades) / len(severidades), _SEVERIDAD_A_NIVEL)
    else:
        nivel_estimado = "sin_datos"

    return AfluenciaEstimada(
        lugar=lugar,
        momento=instante,
        radio_m=radio_m,
        nivel_estimado=nivel_estimado,
        hora=hora_objetivo,
        trafico=trafico,
        ruido=ruido,
        bicimad=bicimad,
        calidad_aire=calidad_aire_lista,
        fuente_grafo=_FUENTE_GRAFO_AFLUENCIA,
        fuentes_gold=fuentes_gold,
    )


def afluencia_estimada(lugar: str, radio_m: float = 300.0, momento: datetime | None = None) -> AfluenciaEstimada:
    """Actividad urbana estimada cerca de un lugar de Madrid (tarea 089,
    sustituye a `afluencia_prevista`/tarea 044 -- ver
    `doc/089-asistente-tool-afluencia-estimada.md`).

    **Por qué esta forma**: el diseño original (tarea 086) elegía
    `aforos_peatones_bicicletas` (conteos reales de peatones/bicicletas)
    como señal primaria; verificado contra Athena/S3 reales (tarea 087) que
    esa fuente municipal está descontinuada desde el 30/6/2024 -- no hay
    ningún dato en vivo que ofrecer desde ahí. En su lugar, esta tool
    combina cuatro señales con datos reales y frescos verificados en la
    misma sesión: tráfico, ruido, ocupación de BiciMAD (todas contribuyen a
    `nivel_estimado`) y calidad del aire (señal más débil/indirecta, solo
    trazabilidad). Ninguna mide peatones directamente -- es una
    aproximación por actividad urbana general, no un conteo de personas.

    Mismo patrón de cruce que `trafico_cercano` (tarea 081), repetido cuatro
    veces: (1) resuelve `lugar` contra `:Lugar` (coincidencia de texto) y
    sigue `PROXIMO_A` hasta cada tipo de nodo dentro de `radio_m`; (2) con
    los identificadores reales encontrados, consulta la tabla Gold
    correspondiente para el valor más reciente en la fecha/hora resuelta.

    Si ninguna de las cuatro señales encuentra ningún nodo dentro de
    `radio_m`, no lanza una excepción: devuelve `AfluenciaEstimada` con
    `nivel_estimado="sin_datos"` y las cuatro listas vacías. Si el grafo
    encuentra nodos pero Gold no tiene fila para la fecha/hora resuelta, se
    listan igualmente con sus valores en `None` -- mismo criterio que
    `trafico_cercano`.

    Args:
        lugar: Nombre o identificador (parcial) de un `:Lugar` del grafo.
        radio_m: Radio de búsqueda en metros. No supera de forma útil el
            umbral de 300m con el que se cargó `PROXIMO_A` (tarea 070).
        momento: Instante a consultar. Si es `None`, se asume el instante
            actual y la hora más reciente con datos disponibles ese día
            para cada señal (pueden diferir entre señales).
    """
    return _afluencia_estimada_impl(lugar, radio_m, momento)


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


def trafico_cercano(
    lugar: str, radio_m: float = 300.0, momento: datetime | None = None
) -> TraficoCercano:
    """Estado del tráfico cerca de un lugar de Madrid (tarea 081: primera
    `tool` que cruza datasets vía el grafo urbano en Neo4j, ver
    `doc/080-cargar-grafo-neo4j-real.md`).

    Cruce en dos pasos: (1) consulta Cypher real contra Neo4j
    (`asistente/neo4j_client.py`) que resuelve `lugar` contra un nodo
    `:Lugar` (coincidencia de texto, case insensitive -- mismo criterio
    pragmático que `calidad_aire` con `zona`, no geocodificación libre) y
    sigue la relación `PROXIMO_A` (tarea 070, umbral de carga 300m) hasta las
    `EstacionMedida` de tipo `"trafico"` a menos de `radio_m`; (2) con los
    `point_id` reales encontrados, consulta `gold.trafico_por_punto_hora`
    (tarea 041, vía Athena) para su estado más reciente.

    Si ningún `:Lugar` coincide con `lugar`, o ninguna `EstacionMedida` de
    tráfico está dentro de `radio_m`, no lanza una excepción: devuelve
    `TraficoCercano` con `resumen="sin_datos"` y `estaciones=[]`. Si el grafo
    encuentra estaciones pero Gold no tiene fila para la fecha/hora resuelta,
    las estaciones se listan igualmente (la proximidad es un dato real y
    trazable en sí mismo) con sus campos de tráfico en `None`.

    `resumen` (`"fluido"`/`"denso"`/`"congestionado"`/`"sin_datos"`) se
    calcula sobre la media de `avg_service_level` (escala real 0-6 de la API
    de tráfico de Madrid, "nivelServicio") entre las estaciones encontradas
    con dato; si ninguna tiene `avg_service_level`, usa como respaldo la
    media de `avg_occupancy_ratio` (0-1). Es una etiqueta simplificada, no
    una métrica oficial -- ver `_clasificar_trafico`.

    Args:
        lugar: Nombre o identificador (parcial) de un `:Lugar` del grafo
            (POI, aparcamiento, cine...) a consultar -- p.ej. "Retiro".
        radio_m: Radio de búsqueda en metros alrededor de `lugar`. No puede
            superar de forma útil el umbral de 300m con el que se cargó
            `PROXIMO_A` (tarea 070): un radio mayor no encontrará relaciones
            que nunca se calcularon, aunque no lanza ningún error por pedirlo.
        momento: Instante para el que se quiere el dato (se usa su fecha y
            hora exacta). Si es `None`, se asume el instante actual (hora de
            Madrid) y se usa la última hora con datos disponibles ese día
            entre las estaciones encontradas.
    """
    return _trafico_cercano_impl(lugar, radio_m, momento)


_RADIO_OPCIONES_MOVILIDAD_M = 300.0  # mismo umbral que PROXIMO_A, tarea 070
_TABLA_EMT = "transporte_publico_emt_por_parada_hora"
_FUENTE_EMT = f"gold.{_TABLA_EMT}"
_FUENTE_GRAFO_OPCIONES_MOVILIDAD = (
    "neo4j: (:Lugar)-[:PROXIMO_A]-(:EstacionMedida{tipo:'trafico'}|:ParadaTransporte{tipo:'bicimad'|'emt'})"
)


def _hora_objetivo_o_reciente(filas: "list[dict]", hora_objetivo: "int | None") -> "int | None":
    if hora_objetivo is not None:
        return hora_objetivo
    return max((fila["hour"] for fila in filas), default=None)


def _trafico_cerca(
    lugar: str, fecha: str, hora_objetivo: "int | None", *, neo4j_driver, athena_client
) -> "str | None":
    """Etiqueta de tráfico (`_clasificar_trafico`) cerca de `lugar`, o
    `None` si `lugar` no resuelve contra ningún `:Lugar` o no hay dato para
    la hora pedida -- reutilizado para origen y destino de
    `opciones_movilidad` (mismo criterio de agregación que
    `_trafico_cercano_impl`, pero aplicado dos veces, una por punto)."""
    query, params = lugares_proximos_a_estaciones_trafico_query(lugar, _RADIO_OPCIONES_MOVILIDAD_M)
    dist = _agregar_por_id(run_neo4j_query(query, params, driver=neo4j_driver))
    if not dist:
        return None
    ids_literal = ", ".join(f"'{sql_literal(pid)}'" for pid in sorted(dist))
    sql = f"""
        SELECT point_id, hour, avg_service_level, avg_occupancy_ratio
        FROM {_TABLA_TRAFICO}
        WHERE date = '{fecha}' AND point_id IN ({ids_literal})
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    hora = _hora_objetivo_o_reciente(filas, hora_objetivo)
    filas_hora = [fila for fila in filas if fila["hour"] == hora]
    niveles = [fila["avg_service_level"] for fila in filas_hora if fila.get("avg_service_level") is not None]
    if niveles:
        return _clasificar_trafico(sum(niveles) / len(niveles), _UMBRALES_SERVICE_LEVEL)
    ratios = [fila["avg_occupancy_ratio"] for fila in filas_hora if fila.get("avg_occupancy_ratio") is not None]
    if ratios:
        return _clasificar_trafico(sum(ratios) / len(ratios), _UMBRALES_OCCUPANCY_RATIO)
    return None


def _bicimad_cerca(
    lugar: str, fecha: str, hora_objetivo: "int | None", campo: str, *, neo4j_driver, athena_client
) -> "float | None":
    """Media de `campo` (`avg_bikes_available` para el origen -- hacen falta
    bicis que coger --, `avg_docks_available` para el destino -- hace falta
    sitio donde dejarla --) entre las paradas BiciMAD cerca de `lugar`, o
    `None` si no hay ninguna o no hay dato para la hora pedida."""
    query, params = lugares_proximos_a_paradas_bicimad_query(lugar, _RADIO_OPCIONES_MOVILIDAD_M)
    dist = _agregar_por_id(run_neo4j_query(query, params, driver=neo4j_driver))
    if not dist:
        return None
    ids_literal = ", ".join(f"'{sql_literal(sid)}'" for sid in sorted(dist))
    sql = f"""
        SELECT station_id, hour, {campo}
        FROM {_TABLA_BICIMAD}
        WHERE date = '{fecha}' AND station_id IN ({ids_literal})
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    hora = _hora_objetivo_o_reciente(filas, hora_objetivo)
    filas_hora = [fila for fila in filas if fila["hour"] == hora]
    valores = [fila[campo] for fila in filas_hora if fila.get(campo) is not None]
    return sum(valores) / len(valores) if valores else None


def _emt_cerca(
    lugar: str, fecha: str, hora_objetivo: "int | None", *, neo4j_driver, athena_client
) -> "float | None":
    """Minutos hasta la próxima llegada estimada (el mejor caso entre las
    paradas EMT cerca de `lugar`, `avg_estimate_arrive_sec` más bajo), o
    `None` si no hay ninguna parada cerca o no hay dato para la hora
    pedida. **Cobertura real muy limitada** (`transporte_publico_emt` solo
    tiene 1 `stop_id` real distinto en Gold, ver `NEXT_STEPS.md` Prioridad
    7) -- esta señal devolverá `None` para casi cualquier origen/destino
    salvo que caiga cerca de esa única parada."""
    query, params = lugares_proximos_a_paradas_emt_query(lugar, _RADIO_OPCIONES_MOVILIDAD_M)
    dist = _agregar_por_id(run_neo4j_query(query, params, driver=neo4j_driver))
    if not dist:
        return None
    ids_literal = ", ".join(f"'{sql_literal(sid)}'" for sid in sorted(dist))
    sql = f"""
        SELECT stop_id, hour, avg_estimate_arrive_sec
        FROM {_TABLA_EMT}
        WHERE date = '{fecha}' AND stop_id IN ({ids_literal})
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    hora = _hora_objetivo_o_reciente(filas, hora_objetivo)
    filas_hora = [fila for fila in filas if fila["hour"] == hora]
    valores = [fila["avg_estimate_arrive_sec"] for fila in filas_hora if fila.get("avg_estimate_arrive_sec") is not None]
    return min(valores) / 60.0 if valores else None


def _opciones_movilidad_impl(
    origen: str,
    destino: str,
    momento: datetime | None,
    *,
    neo4j_driver=None,
    athena_client=None,
) -> "list[OpcionMovilidad]":
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()
    fecha = instante.date().isoformat()
    hora_objetivo = instante.hour if momento is not None else None

    # Si ni origen ni destino resuelven contra ningún :Lugar del grafo, no
    # hay nada que comparar -- lista vacía, mismo criterio que
    # eventos_cercanos. Si solo uno de los dos resuelve, se sigue adelante
    # igualmente: el otro extremo mostrará "sin datos" en las tres
    # opciones, que ya es información real (no hay ningún :Lugar con ese
    # nombre en el grafo).
    origen_resuelto = bool(run_neo4j_query(*resolver_lugar_query(origen), driver=neo4j_driver))
    destino_resuelto = bool(run_neo4j_query(*resolver_lugar_query(destino), driver=neo4j_driver))
    if not origen_resuelto and not destino_resuelto:
        return []

    trafico_origen = _trafico_cerca(origen, fecha, hora_objetivo, neo4j_driver=neo4j_driver, athena_client=athena_client)
    trafico_destino = _trafico_cerca(
        destino, fecha, hora_objetivo, neo4j_driver=neo4j_driver, athena_client=athena_client
    )
    coche = OpcionMovilidad(
        modo="coche",
        incidencias=[
            f"tráfico {trafico_origen} cerca del origen" if trafico_origen else "sin datos de tráfico cerca del origen",
            f"tráfico {trafico_destino} cerca del destino" if trafico_destino else "sin datos de tráfico cerca del destino",
        ],
        fuente_dataset=_FUENTE_TRAFICO,
    )

    bicis_origen = _bicimad_cerca(
        origen, fecha, hora_objetivo, "avg_bikes_available", neo4j_driver=neo4j_driver, athena_client=athena_client
    )
    anclajes_destino = _bicimad_cerca(
        destino, fecha, hora_objetivo, "avg_docks_available", neo4j_driver=neo4j_driver, athena_client=athena_client
    )
    bicimad = OpcionMovilidad(
        modo="bicimad",
        incidencias=[
            f"{bicis_origen:.1f} bicis disponibles de media cerca del origen"
            if bicis_origen is not None
            else "sin datos de BiciMAD cerca del origen",
            f"{anclajes_destino:.1f} anclajes libres de media cerca del destino"
            if anclajes_destino is not None
            else "sin datos de BiciMAD cerca del destino",
        ],
        fuente_dataset=_FUENTE_BICIMAD,
    )

    espera_origen = _emt_cerca(origen, fecha, hora_objetivo, neo4j_driver=neo4j_driver, athena_client=athena_client)
    espera_destino = _emt_cerca(destino, fecha, hora_objetivo, neo4j_driver=neo4j_driver, athena_client=athena_client)
    transporte_publico = OpcionMovilidad(
        modo="transporte_publico",
        incidencias=[
            f"próxima llegada estimada en {espera_origen:.1f} min cerca del origen"
            if espera_origen is not None
            else "sin datos de EMT cerca del origen",
            f"próxima llegada estimada en {espera_destino:.1f} min cerca del destino"
            if espera_destino is not None
            else "sin datos de EMT cerca del destino",
        ],
        fuente_dataset=_FUENTE_EMT,
    )

    return [coche, transporte_publico, bicimad]


def opciones_movilidad(
    origen: str, destino: str, momento: datetime | None = None
) -> "list[OpcionMovilidad]":
    """Alternativas de desplazamiento entre dos puntos de Madrid (tarea 096:
    implementación real, ver `asistente/README.md`).

    **Simplificación deliberada, distinta al resto de `tools`**: esta `tool`
    no calcula una ruta real ni una duración de viaje (`duracion_estimada_
    min` queda siempre en `None`) -- no existe ningún grafo de calles/red
    viaria transitable en este proyecto (`CONECTADO_CON`, tarea 071, solo
    conecta paradas de transporte público a lo largo de una línea CRTM, no
    calles/aceras entre dos puntos cualesquiera). En su lugar, resuelve
    `origen`/`destino` por separado contra `:Lugar` (mismo criterio que
    `trafico_cercano`/`eventos_cercanos`) y describe, para cada modo, las
    condiciones reales encontradas cerca de cada extremo (tráfico cerca de
    origen y destino; bicis disponibles cerca del origen y anclajes libres
    cerca del destino; próxima llegada EMT estimada cerca de cada extremo) --
    un routing real por calles/líneas de transporte queda fuera de alcance
    hasta que exista un grafo transitable de verdad.

    La señal de `transporte_publico` tiene cobertura real muy limitada:
    `transporte_publico_emt` solo tiene 1 `stop_id` real distinto en Gold
    (`NEXT_STEPS.md`, Prioridad 7) -- casi cualquier origen/destino
    devolverá "sin datos de EMT" para ambos extremos, no es un fallo de esta
    `tool`.

    Si ni `origen` ni `destino` coinciden con ningún `:Lugar` del grafo, no
    lanza una excepción: devuelve una lista vacía. Si solo uno de los dos
    coincide, se devuelven igualmente las 3 opciones -- el extremo sin
    `:Lugar` aparece como "sin datos" en las tres, que ya es información
    real (no hay ningún lugar con ese nombre en el grafo).

    Args:
        origen: Nombre o identificador (parcial) de un `:Lugar` del grafo
            como punto de partida -- p.ej. "Retiro".
        destino: Ídem como punto de llegada -- p.ej. "Sol".
        momento: Instante del desplazamiento (se usa su fecha y hora
            exacta). Si es `None`, se asume el instante actual (hora de
            Madrid) y se usa la última hora con datos disponibles ese día
            en cada señal.
    """
    return _opciones_movilidad_impl(origen, destino, momento)


def disponibilidad_aparcamiento(zona: str, momento: datetime | None = None) -> DisponibilidadAparcamiento:
    """Plazas de aparcamiento libres estimadas en una zona de Madrid (tarea
    090: implementación real, ver `asistente/README.md`).

    Fuente: `gold.aparcamientos_por_parking_hora` (mediciones reales de
    `ingesta.capturas.aparcamientos_madrid`, tarea 005), consultada vía
    Athena. Mismo criterio pragmático de resolución de `zona` que
    `calidad_aire`: coincidencia de texto (case insensitive, `LIKE '%zona%'`)
    contra `name`/`parking_id` -- no hay resolución por barrio/distrito
    todavía (pendiente del grafo).

    A diferencia de `calidad_aire` (que agrega tomando el peor caso entre
    estaciones que coinciden), aquí varios aparcamientos que coinciden con
    `zona` representan capacidad real distinta y aditiva: `plazas_libres`/
    `plazas_totales` son la suma entre todos los aparcamientos encontrados,
    no el de uno solo -- ver `_disponibilidad_aparcamiento_impl`.

    Si ningún aparcamiento coincide (o no hay datos para la hora pedida), no
    lanza una excepción: devuelve `DisponibilidadAparcamiento` con
    `aparcamientos_consultados=[]` y `plazas_libres`/`plazas_totales=None`.

    Args:
        zona: Nombre o identificador (parcial) de uno o varios aparcamientos
            públicos de Madrid a consultar -- p.ej. "Plaza de Oriente".
        momento: Instante para el que se quiere el dato (se usa su fecha y
            hora exacta). Si es `None`, se asume el instante actual (hora de
            Madrid) y se usa la última hora con datos disponibles ese día.
    """
    return _disponibilidad_aparcamiento_impl(zona, momento)


# Tabla Silver, no Gold (tarea 095 -- caso deliberadamente distinto al resto
# de `tools`): Gold de este dataset (`agenda_eventos_por_categoria_
# distrito_fecha`) agrega por categoría/distrito/fecha, sin lat/lon por
# evento individual -- no sirve para "eventos cerca de un punto". Silver sí
# conserva lat/lon reales por evento (`ingesta.capturas.agenda_eventos_madrid`,
# tarea 017/056), ya validados por la puerta de calidad de
# `procesamiento/silver_gold/agenda_eventos/transform.py`.
_TABLA_AGENDA_EVENTOS_SILVER = "agenda_eventos"
_FUENTE_AGENDA_EVENTOS_SILVER = f"silver.{_TABLA_AGENDA_EVENTOS_SILVER}"
_FUENTE_GRAFO_EVENTOS_CERCANOS = "neo4j: (:Lugar) -- resuelve solo el punto de referencia, sin PROXIMO_A"

# Ventana hacia delante desde `momento` en la que se buscan eventos (tarea
# 095): Silver de `agenda_eventos` tiene cientos de particiones `fecha=`
# reales que llegan hasta 2029 (eventos anunciados con mucha antelación,
# ver doc/095-...md) -- sin acotar, "eventos cercanos" incluiría conciertos
# de dentro de 3 años. 30 días cubre "próximos" de forma razonable sin
# convertirse en un escaneo de toda la tabla.
_VENTANA_DIAS_EVENTOS_CERCANOS = 30

_EARTH_RADIUS_M = 6371000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos puntos WGS84 (fórmula del semiverseno).

    Réplica deliberada de `grafo/geo.py::haversine_m` en vez de importarla
    -- mismo criterio ya documentado en `asistente/timeutils.py`/`athena.py`:
    `asistente/` se mantiene autocontenido, sin depender de `grafo/`.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _eventos_cercanos_impl(
    lugar: str,
    radio_m: float,
    momento: datetime | None,
    *,
    neo4j_driver=None,
    athena_client=None,
) -> "list[EventoCercano]":
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()

    query, params = resolver_lugar_query(lugar)
    filas_lugar = run_neo4j_query(query, params, driver=neo4j_driver)
    candidatos = [
        (fila["lat"], fila["lon"]) for fila in filas_lugar if fila.get("lat") is not None and fila.get("lon") is not None
    ]
    if not candidatos:
        return []

    fecha_inicio = instante.date()
    fecha_fin = fecha_inicio + timedelta(days=_VENTANA_DIAS_EVENTOS_CERCANOS)
    # `fecha` (no `date`): a diferencia de Gold -- que renombra la partición
    # a `date` al agregar, ver p.ej. `.withColumnRenamed("fecha", "date")`
    # en `procesamiento/silver_gold/*/glue_silver_to_gold.py` -- Silver
    # conserva su columna de partición original en español. Bug real
    # encontrado verificando esta tool contra Athena real (`COLUMN_NOT_FOUND:
    # 'date'`), ver doc/095-...md.
    sql = f"""
        SELECT event_id, title, venue_name, lat, lon, start_datetime
        FROM {_TABLA_AGENDA_EVENTOS_SILVER}
        WHERE fecha BETWEEN '{fecha_inicio.isoformat()}' AND '{fecha_fin.isoformat()}'
    """
    filas_eventos = run_athena_query(sql, SILVER_DATABASE, athena_client=athena_client)

    # Silver es un almacén persistente, no deduplicado: el mismo evento
    # recibe una fila nueva cada día de ingestión en que la fuente lo sigue
    # listando mientras sigue vigente (ver docstring de
    # `procesamiento/silver_gold/agenda_eventos/glue_silver_to_gold.py`) --
    # confirmado contra datos reales en la tarea 095 (un mismo `event_id`
    # apareció repetido en la respuesta antes de este `dict`). Se queda con
    # una sola fila por `event_id` antes de calcular distancias.
    filas_por_evento = {}
    for fila in filas_eventos:
        event_id = fila.get("event_id")
        if event_id and event_id not in filas_por_evento:
            filas_por_evento[event_id] = fila

    resultado: "list[EventoCercano]" = []
    for fila in filas_por_evento.values():
        lat, lon = fila.get("lat"), fila.get("lon")
        inicio = fila.get("start_datetime")
        if lat is None or lon is None or not inicio:
            # Sin coordenadas o sin hora de inicio, este evento no puede
            # participar en un filtro de distancia ni ordenarse -- se
            # excluye en vez de forzar un valor inventado (mismo criterio
            # que el resto del patrón: no hay tantos eventos sin lat/lon
            # como para que valga la pena una segunda vía de resolución).
            continue
        distancia_m = min(_haversine_m(lat, lon, clat, clon) for clat, clon in candidatos)
        if distancia_m <= radio_m:
            resultado.append(
                EventoCercano(
                    nombre=fila.get("title") or fila.get("event_id"),
                    lugar=fila.get("venue_name") or "",
                    distancia_m=distancia_m,
                    inicio=inicio,
                    fuente_dataset=_FUENTE_AGENDA_EVENTOS_SILVER,
                )
            )

    resultado.sort(key=lambda evento: evento.distancia_m)
    return resultado


def eventos_cercanos(
    lugar: str, radio_m: float = 500.0, momento: datetime | None = None
) -> "list[EventoCercano]":
    """Eventos con actividad cerca de un lugar de Madrid, dentro de los
    próximos 30 días (tarea 095: implementación real, ver
    `asistente/README.md`).

    Cruce en dos pasos, distinto al de `trafico_cercano`/`afluencia_estimada`
    (que siguen `PROXIMO_A` hasta un nodo del grafo): (1) resuelve `lugar`
    contra `:Lugar` (coincidencia de texto, ver `resolver_lugar_query`) y
    toma sus coordenadas -- no hay ningún nodo `:Evento` en el grafo
    todavía; (2) consulta **Silver** de `agenda_eventos` (no Gold, que
    agrega por categoría/distrito/fecha sin lat/lon por evento -- ver
    `_TABLA_AGENDA_EVENTOS_SILVER`) para la ventana `[momento, momento+30
    días)`, y filtra por distancia real (Haversine, `_haversine_m`) a
    cualquiera de los `:Lugar` coincidentes.

    Si ningún `:Lugar` coincide con `lugar`, o ningún evento de Silver está
    dentro de `radio_m` en esa ventana, no lanza una excepción: devuelve una
    lista vacía. Los resultados se ordenan por `distancia_m` ascendente.

    **`agenda_recintos_madrid` (tarea 022) queda fuera de esta tarea**: solo
    tiene captura de muestra a Bronze, sin ningún pipeline Silver/Gold
    construido todavía (a diferencia de `agenda_eventos`) -- no hay tabla
    real que consultar.

    Args:
        lugar: Nombre o identificador (parcial) de un `:Lugar` del grafo
            (POI, aparcamiento, cine...) a consultar -- p.ej. "Retiro".
        radio_m: Radio de búsqueda en metros alrededor de `lugar`.
        momento: Instante de referencia; se buscan eventos cuyo
            `start_datetime` cae entre `momento` y `momento` + 30 días. Si es
            `None`, se asume el instante actual (hora de Madrid).
    """
    return _eventos_cercanos_impl(lugar, radio_m, momento)


# --- calidad_aire_prevista (ML_09) -------------------------------------------

_HORIZONTES_PREVISTA = (1, 3, 6)


def _historial_por_hora(
    filas: "list[dict]", station_id: str, pollutant: str
) -> "tuple[float | None, dict[int, float], float | None, float | None, datetime | None]":
    """De las filas de Gold, para `(station_id, pollutant)`: el valor de la
    **última hora con lectura** (el "ahora" efectivo -- Gold va con varias
    horas de retraso, así que el forecast se ancla al último dato real, igual
    que las features del feature store de `ML_01`), un mapa
    `{horas_atrás: avg_value}` para 1..24 respecto a ese ancla, la lat/lon y
    el `datetime` del ancla."""
    puntos: "dict[datetime, float]" = {}
    lat = lon = None
    for f in filas:
        if f.get("station_id") != station_id or f.get("pollutant") != pollutant:
            continue
        if f.get("avg_value") is None:
            continue
        lat = f.get("lat", lat)
        lon = f.get("lon", lon)
        dt = datetime.fromisoformat(f["date"]).replace(hour=int(f["hour"]))
        puntos[dt] = float(f["avg_value"])
    if not puntos:
        return None, {}, lat, lon, None
    ancla = max(puntos)
    historial = {
        k: puntos[ancla - timedelta(hours=k)]
        for k in range(1, 25)
        if (ancla - timedelta(hours=k)) in puntos
    }
    return puntos[ancla], historial, lat, lon, ancla


def _calidad_aire_prevista_impl(
    zona: str, horizonte_horas: int, momento: datetime | None, *, athena_client=None
) -> CalidadAirePrevista:
    if horizonte_horas not in _HORIZONTES_PREVISTA:
        raise ValueError(
            f"horizonte_horas debe ser uno de {_HORIZONTES_PREVISTA}; recibido {horizonte_horas}"
        )
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()

    hoy = instante.date()
    ayer = (instante - timedelta(days=1)).date()
    zona_literal = sql_literal(zona.lower())
    sql = f"""
        SELECT station_id, station_name, pollutant, unit, date, hour,
               avg_value, lat, lon
        FROM {_TABLA_CALIDAD_AIRE}
        WHERE date IN ('{ayer.isoformat()}', '{hoy.isoformat()}')
          AND (lower(station_name) LIKE '%{zona_literal}%'
               OR lower(station_id) LIKE '%{zona_literal}%')
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)

    fuente = _FUENTE_CALIDAD_AIRE
    if not filas:
        return CalidadAirePrevista(
            zona=zona, momento=instante, horizonte_horas=horizonte_horas, fuente_dataset=fuente,
        )

    # elige (estación, contaminante): el de mayor ratio vs límite de
    # referencia en su lectura más reciente -- mismo criterio conservador que
    # `_calidad_aire_impl` (peor caso), pero fijando una sola estación.
    ultima_por_par: "dict[tuple[str, str], dict]" = {}
    for f in filas:
        if f.get("avg_value") is None:
            continue
        par = (f["station_id"], f["pollutant"])
        prev = ultima_por_par.get(par)
        clave = (f["date"], int(f["hour"]))
        if prev is None or clave > (prev["date"], int(prev["hour"])):
            ultima_por_par[par] = f
    if not ultima_por_par:
        return CalidadAirePrevista(
            zona=zona, momento=instante, horizonte_horas=horizonte_horas, fuente_dataset=fuente,
        )

    def _ratio(f: dict) -> float:
        lim = _LIMITES_REFERENCIA_UGM3.get(f["pollutant"])
        return (f["avg_value"] / lim) if lim else -1.0

    (station_id, pollutant), fila_ref = max(ultima_por_par.items(), key=lambda kv: _ratio(kv[1]))

    actual, historial, lat, lon, ancla = _historial_por_hora(filas, station_id, pollutant)
    if actual is None or ancla is None:
        return CalidadAirePrevista(
            zona=zona, momento=instante, horizonte_horas=horizonte_horas, fuente_dataset=fuente,
        )
    # el forecast se ancla en la última hora con lectura real (Gold va con
    # retraso); `momento` de la respuesta = ese ancla.
    vector, completeness = prevision.construir_features(
        actual, historial, instante=ancla, lat=lat, lon=lon,
    )
    if not prevision.modelo_disponible(horizonte_horas):
        return CalidadAirePrevista(
            zona=zona, momento=ancla, horizonte_horas=horizonte_horas,
            estacion=fila_ref.get("station_name") or station_id, contaminante=pollutant,
            valor_actual=round(actual, 1), unidad=fila_ref.get("unit"),
            data_completeness=round(completeness, 2), fuente_dataset=fuente,
        )

    previsto = prevision.predecir(vector, horizonte=horizonte_horas)
    limite = _LIMITES_REFERENCIA_UGM3.get(pollutant)
    nivel = _clasificar_indice(previsto / limite) if limite else "sin_clasificar"

    return CalidadAirePrevista(
        zona=zona,
        momento=ancla,
        horizonte_horas=horizonte_horas,
        estacion=fila_ref.get("station_name") or station_id,
        contaminante=pollutant,
        valor_previsto=round(previsto, 1),
        valor_actual=round(actual, 1),
        unidad=fila_ref.get("unit"),
        nivel_previsto=nivel,
        data_completeness=round(completeness, 2),
        modelo=f"calidad_aire_h{horizonte_horas}.onnx (ML_07 / madrono-calidad_aire-h{horizonte_horas})",
        fuente_dataset=fuente,
    )


def calidad_aire_prevista(
    zona: str, horizonte_horas: int = 6, momento: datetime | None = None
) -> CalidadAirePrevista:
    """Previsión de calidad del aire para una estación de Madrid a 1, 3 o 6 h
    vista (tarea `ML_09`, cierra el bucle observación→predicción→asistente de
    la memoria §6.7 / §4.1).

    Sirve la cifra corriendo el modelo **ONNX** de `ML_07` (LightGBM
    multi-horizonte de `ML_03`, exportado) sobre las 19 features de
    `modelado/export/CONTRATO.md`, construidas a partir de las últimas 24 h
    de `gold.calidad_aire_por_estacion_contaminante_hora` (Athena, mismo
    patrón que `calidad_aire`). El `.onnx` está vendido en
    `asistente/modelos/` (copia del artefacto de `modelado.export.to_onnx`).

    `zona` se resuelve por coincidencia de texto sobre
    `station_name`/`station_id` (igual que `calidad_aire`: no hay resolución
    por barrio/distrito). Entre las estaciones/contaminantes que coinciden se
    fija el de mayor ratio frente a su límite de referencia (peor caso).

    Devuelve `CalidadAirePrevista` con `valor_previsto` (µg/m³ a
    `horizonte_horas`), `valor_actual`, `nivel_previsto` (índice simplificado,
    igual que `calidad_aire`) y `data_completeness` (0..1): baja cuando
    faltan lecturas históricas para construir las features. Si no hay
    ninguna estación coincidente devuelve `nivel_previsto="sin_datos"` sin
    lanzar excepción.

    Args:
        zona: Nombre o identificador (parcial) de una estación de la red de
            calidad del aire de Madrid.
        horizonte_horas: Horas por delante a prever. Uno de 1, 3 o 6.
        momento: Instante de referencia (ISO 8601). Si es `None`, ahora
            (hora de Madrid).
    """
    return _calidad_aire_prevista_impl(zona, horizonte_horas, momento)


# ---------------------------------------------------------------------------
# trafico_prevista (FIL_13) -- misma mecánica que calidad_aire_prevista pero
# sobre `avg_service_level` de un punto de tráfico resuelto por el grafo.
# ---------------------------------------------------------------------------

_FUENTE_GRAFO_TRAFICO_PREVISTA = _FUENTE_GRAFO_TRAFICO_CERCANO


def _historial_trafico_por_hora(
    filas: "list[dict]", point_id: str
) -> "tuple[float | None, dict[int, float], float | None, float | None, datetime | None]":
    """De las filas de Gold para `point_id`: `avg_service_level` de la última
    hora con lectura (ancla), `{horas_atrás: valor}` para 1..24 respecto al
    ancla, lat/lon y el `datetime` del ancla. Mismo criterio que
    `_historial_por_hora` de calidad del aire."""
    puntos: "dict[datetime, float]" = {}
    lat = lon = None
    for f in filas:
        if str(f.get("point_id")) != str(point_id) or f.get("avg_service_level") is None:
            continue
        lat = f.get("lat", lat)
        lon = f.get("lon", lon)
        dt = datetime.fromisoformat(f["date"]).replace(hour=int(f["hour"]))
        puntos[dt] = float(f["avg_service_level"])
    if not puntos:
        return None, {}, lat, lon, None
    ancla = max(puntos)
    historial = {
        k: puntos[ancla - timedelta(hours=k)]
        for k in range(1, 25)
        if (ancla - timedelta(hours=k)) in puntos
    }
    return puntos[ancla], historial, lat, lon, ancla


def _trafico_prevista_impl(
    lugar: str,
    horizonte_horas: int,
    radio_m: float,
    momento: datetime | None,
    *,
    neo4j_driver=None,
    athena_client=None,
) -> TraficoPrevista:
    if horizonte_horas not in _HORIZONTES_PREVISTA:
        raise ValueError(
            f"horizonte_horas debe ser uno de {_HORIZONTES_PREVISTA}; recibido {horizonte_horas}"
        )
    if momento is not None:
        instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
    else:
        instante = now_madrid()

    fuente = _FUENTE_TRAFICO

    def _sin(**kw) -> TraficoPrevista:
        base = dict(
            lugar=lugar, momento=instante, horizonte_horas=horizonte_horas,
            fuente_dataset=fuente, fuente_grafo=_FUENTE_GRAFO_TRAFICO_PREVISTA,
        )
        base.update(kw)
        return TraficoPrevista(**base)

    # 1. puntos de tráfico cerca del lugar (grafo)
    query, params = lugares_proximos_a_estaciones_trafico_query(lugar, radio_m)
    filas_grafo = run_neo4j_query(query, params, driver=neo4j_driver)
    if not filas_grafo:
        return _sin()
    distancia_por_point_id: "dict[str, float]" = {}
    for fila in filas_grafo:
        estacion_id = fila.get("estacion_id") or ""
        pid = estacion_id.split(":", 1)[1] if ":" in estacion_id else None
        if not pid:
            continue
        d = distancia_por_point_id.get(pid)
        if d is None or fila["distancia_m"] < d:
            distancia_por_point_id[pid] = fila["distancia_m"]
    if not distancia_por_point_id:
        return _sin()

    # 2. últimas ~2 fechas de Gold para esos puntos (Gold va con retraso; el
    #    forecast se ancla en la última hora real, igual que calidad del aire)
    hoy = instante.date()
    ayer = (instante - timedelta(days=1)).date()
    ids_literal = ", ".join(f"'{sql_literal(pid)}'" for pid in sorted(distancia_por_point_id))
    sql = f"""
        SELECT point_id, date, hour, avg_service_level, lat, lon
        FROM {_TABLA_TRAFICO}
        WHERE date IN ('{ayer.isoformat()}', '{hoy.isoformat()}')
          AND point_id IN ({ids_literal})
          AND avg_service_level IS NOT NULL
    """
    filas = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    if not filas:
        return _sin()

    # 3. punto de referencia: el de mayor avg_service_level en su lectura más
    #    reciente (peor caso, mismo criterio que calidad del aire con el ratio)
    ultima_por_pid: "dict[str, dict]" = {}
    for f in filas:
        pid = str(f["point_id"])
        prev = ultima_por_pid.get(pid)
        clave = (f["date"], int(f["hour"]))
        if prev is None or clave > (prev["date"], int(prev["hour"])):
            ultima_por_pid[pid] = f
    point_id = max(ultima_por_pid, key=lambda p: ultima_por_pid[p]["avg_service_level"])

    actual, historial, lat, lon, ancla = _historial_trafico_por_hora(filas, point_id)
    if actual is None or ancla is None:
        return _sin(punto_id=point_id)

    vector, completeness = prevision.construir_features(
        actual, historial, instante=ancla, lat=lat, lon=lon,
    )
    fechas = sorted({f["date"] for f in filas if str(f["point_id"]) == point_id})
    ventana = f"{fechas[0]}..{fechas[-1]}" if fechas else None

    if not prevision.modelo_disponible(horizonte_horas, target="trafico"):
        return _sin(
            punto_id=point_id, momento=ancla, valor_actual=round(actual, 2),
            nivel_previsto=_clasificar_trafico(actual, _UMBRALES_SERVICE_LEVEL),
            data_completeness=round(completeness, 2), ventana_datos=ventana,
        )

    previsto = prevision.predecir(vector, horizonte=horizonte_horas, target="trafico")
    return TraficoPrevista(
        lugar=lugar,
        momento=ancla,
        horizonte_horas=horizonte_horas,
        punto_id=point_id,
        valor_previsto=round(previsto, 2),
        valor_actual=round(actual, 2),
        nivel_previsto=_clasificar_trafico(previsto, _UMBRALES_SERVICE_LEVEL),
        data_completeness=round(completeness, 2),
        modelo=f"trafico_h{horizonte_horas}.onnx (ML_07 / madrono-trafico-h{horizonte_horas})",
        ventana_datos=ventana,
        fuente_dataset=fuente,
        fuente_grafo=_FUENTE_GRAFO_TRAFICO_PREVISTA,
    )


def trafico_prevista(
    lugar: str, horizonte_horas: int = 6, radio_m: float = 300.0, momento: datetime | None = None
) -> TraficoPrevista:
    """Previsión de congestión de tráfico cerca de un lugar de Madrid a 1, 3
    o 6 h vista (`FIL_13`, mismo bucle observación→predicción→asistente que
    `calidad_aire_prevista`).

    Resuelve los puntos de medida de tráfico a `radio_m` del lugar cruzando
    el grafo urbano (`:Lugar`-[:PROXIMO_A]-`:EstacionMedida {tipo:'trafico'}`,
    igual que `trafico_cercano`), fija el punto de peor caso (mayor
    `avg_service_level` reciente), construye las 19 features de
    `modelado/export/CONTRATO.md` con sus últimas 24 h de
    `gold.trafico_por_punto_hora` y corre el modelo **ONNX** de `ML_07`
    (`madrono-trafico-h<H>@champion`). El `.onnx` está vendido en
    `asistente/modelos/`.

    Devuelve `TraficoPrevista` con `valor_previsto` (`avg_service_level`,
    0=fluido..6=cortado), `valor_actual`, `nivel_previsto`
    (`fluido`/`denso`/`congestionado`, mismas bandas que `trafico_cercano`) y
    `data_completeness` (0..1). Si no hay ningún punto de tráfico cerca, o
    Gold no tiene lecturas para construir las features, devuelve
    `nivel_previsto="sin_datos"` sin lanzar excepción.

    Args:
        lugar: Nombre (parcial) de un lugar de Madrid (se resuelve por texto
            en el grafo, igual que `trafico_cercano`).
        horizonte_horas: Horas por delante a prever. Uno de 1, 3 o 6.
        radio_m: Radio de búsqueda de puntos de tráfico alrededor del lugar.
        momento: Instante de referencia (ISO 8601). Si es `None`, ahora
            (hora de Madrid).
    """
    return _trafico_prevista_impl(lugar, horizonte_horas, radio_m, momento)
