"""`tools` del agente MCP de Madroño (tarea 044; primera con lógica real,
`calidad_aire`, tarea 079).

La memoria del TFM (apartado 6.7) describe el asistente respondiendo
preguntas de movilidad y vida urbana apoyándose en varias señales: afluencia
estimada, calidad del aire, opciones de movilidad, disponibilidad de
aparcamiento y eventos cercanos. Estas cinco funciones anticipan esa
interfaz (firma y docstring, registradas como `tools` MCP en
`asistente/mcp_agent/server.py`) a partir de lo que `ingesta/` ya captura
hoy. `calidad_aire` (tarea 079), `trafico_cercano` (tarea 081),
`afluencia_estimada` (tarea 089, sustituye a la `afluencia_prevista`
original -- ver su docstring) y `disponibilidad_aparcamiento` (tarea 090)
ya leen datos reales; `opciones_movilidad` y `eventos_cercanos` siguen
levantando `NotImplementedError` -- tareas de seguimiento separadas, sin
bloqueo técnico, solo alcance.

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
    AfluenciaEstimada,
    CalidadAireZona,
    DisponibilidadAparcamiento,
    EstacionCalidadAireCercana,
    EstacionRuidoCercana,
    EstacionTraficoCercana,
    EventoCercano,
    OpcionMovilidad,
    ParadaBicimadCercana,
    TraficoCercano,
)
from asistente.neo4j_client import (
    lugares_proximos_a_estaciones_calidad_aire_query,
    lugares_proximos_a_estaciones_ruido_query,
    lugares_proximos_a_estaciones_trafico_query,
    lugares_proximos_a_paradas_bicimad_query,
    run_neo4j_query,
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
