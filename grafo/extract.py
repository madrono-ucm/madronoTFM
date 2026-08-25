"""Extracción real de Silver/Gold (vía Athena) y Bronze (vía S3 directo) para
alimentar `grafo.nodos`/`grafo.relaciones` (tarea 067) con datos reales, en
vez de fixtures en memoria.

**Decisión ya tomada por el enunciado de la tarea 069 (no reabierta aquí)**:
leer Gold vía **Athena** (`boto3` + `start_query_execution`/
`get_query_results`, mismo patrón que ya verificó la tarea 066 con datos de
producción reales), no releer los ficheros Parquet directamente con
`pyarrow`/`pandas` -- evita duplicar la lógica de particionado que ya
resuelve el catálogo de Glue (tarea 068, Partition Projection) y mantiene una
única vía de lectura para todo lo que consuma Silver/Gold desde fuera de
Glue. Los tres orígenes que nunca tuvieron Silver/Gold
(`barrios_distritos_madrid` -- distritos y barrios por separado --,
`poi_madrid`, `crtm_red_transporte_madrid`) no tienen tabla en el catálogo,
así que se leen directamente como JSON de S3 (mismo bucket/convención de
prefijo que `ingesta/capturas/bronze.py::BronzeWriter`:
`<dataset>/fecha=YYYY-MM-DD/hora=HH/<archivo>.json`).

## Por qué `GROUP BY <id> ... max_by(<col>, date)` y no el histórico completo

Gold es una serie temporal (una fila por punto/estación **y hora**, o por
parking/cine **y día**); un nodo del grafo es una entidad única y su
identidad/ubicación es, en la práctica, constante en el tiempo (mismo
criterio que ya documenta `grafo/nodos.py::dedupe_nodes`). Traer todo el
histórico de cada dataset para quedarse solo con `id`/`nombre`/`lat`/`lon`
sería escanear muchos más bytes de los necesarios (para `trafico`, cientos de
millones de filas a fecha de la tarea 068) -- cada consulta de este módulo
agrega en el propio Athena con `GROUP BY <id>` y `max_by(<col>, date)` (se
queda con el valor de la fila con la fecha más reciente dentro de la
ventana), acotando además el escaneo a los últimos `_RECENT_WINDOW_DAYS` días
con un filtro de partición (Athena solo lee esas particiones gracias a la
Partition Projection de la tarea 068).

## `lat`/`lon` planas (Gold) -> `location` anidada (lo que espera `nodos.py`)

Gold aplana la ubicación a columnas `lat`/`lon` (`infra/terraform/glue.tf`);
`grafo.nodos._location()` espera, en cambio, `record["location"] = {"lat":
..., "lon": ...}` (la misma forma que ya usan Silver/Bronze). `_nest_location`
hace esa traducción -- la única razón de ser de esta función-- para no tener
que tocar `nodos.py` (que ya está testado y no le corresponde saber de dónde
vienen sus columnas).

## Tipos de columna de Athena

`get_query_results` devuelve **todos** los valores como `VarCharValue`
(texto), independientemente del tipo real de la columna (`double`, `bigint`,
...) -- comportamiento documentado de la API de Athena, no un bug de este
módulo. `_cast_athena_value` los convierte de vuelta a `int`/`float` según
`ResultSetMetadata.ColumnInfo[].Type`, para que `lat`/`lon` lleguen a
`grafo/cypher.py::Neo4jLoader` como números reales (necesarios para
`point({latitude: $lat, longitude: $lon, ...})` en Cypher) y no como cadenas.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import boto3

# ---------------------------------------------------------------------------
# Configuración real (tareas 065/066/068) -- sobrescribible por variable de
# entorno para tests/otros entornos, con el valor real de esta cuenta
# (`eu-west-1`, `222234418587`) como default.
# ---------------------------------------------------------------------------

ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "madrono-tfm-dev-silver-gold")
SILVER_DATABASE = os.environ.get("ATHENA_SILVER_DATABASE", "madrono-tfm_dev_silver")
GOLD_DATABASE = os.environ.get("ATHENA_GOLD_DATABASE", "madrono-tfm_dev_gold")
BRONZE_BUCKET = os.environ.get("BRONZE_BUCKET", "madrono-tfm-dev-bronze-222234418587")

# Ventana de días sobre la que se agrega cada consulta Gold (ver docstring del
# módulo, "Por qué GROUP BY... y no el histórico completo").
_RECENT_WINDOW_DAYS = 14

_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}
_INTEGER_TYPES = {"tinyint", "smallint", "integer", "int", "bigint"}
_FLOAT_TYPES = {"float", "double", "decimal", "real"}


def _cast_athena_value(value: Optional[str], athena_type: str):
    """`get_query_results` siempre devuelve texto (`VarCharValue`) -- lo
    convierte de vuelta según el tipo real de columna (`ResultSetMetadata`)."""
    if value is None:
        return None
    if athena_type in _INTEGER_TYPES:
        try:
            return int(value)
        except ValueError:
            return value
    if athena_type in _FLOAT_TYPES:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _recent_date_filter(column: str = "date") -> str:
    """Filtro de partición para acotar el escaneo a los últimos
    `_RECENT_WINDOW_DAYS` días (comparación de texto: los valores de
    partición son `string` con formato `yyyy-MM-dd`, que ordena igual que un
    `date` real)."""
    return (
        f"{column} >= date_format(date_add('day', -{_RECENT_WINDOW_DAYS}, current_date), '%Y-%m-%d')"
    )


def run_athena_query(
    sql: str,
    database: str,
    *,
    athena_client=None,
    workgroup: Optional[str] = None,
    poll_interval_seconds: float = 1.0,
    max_wait_seconds: float = 120.0,
) -> "list[dict]":
    """Lanza `sql` contra `database` en el workgroup `madrono-tfm-dev-silver-gold`
    (tarea 066) y espera el resultado con un bucle de sondeo de backoff corto
    (mismo patrón documentado en `doc/066-consulta-athena-silver-gold.md`).

    `athena_client` es inyectable (por defecto, `boto3.client("athena")`) para
    poder testear el parseo sin credenciales/conexión real -- ver
    `grafo/tests/test_extract.py`.
    """
    client = athena_client or boto3.client("athena")
    workgroup = workgroup or ATHENA_WORKGROUP

    execution_id = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
    )["QueryExecutionId"]

    elapsed = 0.0
    while True:
        execution = client.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state in _TERMINAL_STATES:
            break
        if elapsed >= max_wait_seconds:
            raise TimeoutError(
                f"La consulta Athena {execution_id} no terminó en {max_wait_seconds}s (sigue en estado {state})"
            )
        time.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds

    if state != "SUCCEEDED":
        reason = execution["Status"].get("StateChangeReason", "sin motivo reportado")
        raise RuntimeError(f"La consulta Athena {execution_id} terminó en estado {state}: {reason}")

    return _collect_results(client, execution_id)


def _collect_results(client, execution_id: str) -> "list[dict]":
    rows: "list[dict]" = []
    columns = None
    next_token = None
    first_page = True

    while True:
        kwargs = {"QueryExecutionId": execution_id}
        if next_token:
            kwargs["NextToken"] = next_token
        page = client.get_query_results(**kwargs)

        if columns is None:
            columns = page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]

        data_rows = page["ResultSet"]["Rows"]
        if first_page:
            data_rows = data_rows[1:]  # la primera fila es siempre la cabecera
            first_page = False

        for row in data_rows:
            values = [cell.get("VarCharValue") for cell in row["Data"]]
            rows.append(
                {
                    col["Name"]: _cast_athena_value(value, col["Type"])
                    for col, value in zip(columns, values)
                }
            )

        next_token = page.get("NextToken")
        if not next_token:
            break

    return rows


def _nest_location(row: dict) -> dict:
    """`row` trae `lat`/`lon` planas (Gold, ver docstring del módulo) --
    las envuelve en `{"location": {"lat": ..., "lon": ...}}`, la forma que
    espera `grafo.nodos._location()`."""
    result = dict(row)
    lat = result.pop("lat", None)
    lon = result.pop("lon", None)
    result["location"] = {"lat": lat, "lon": lon}
    return result


# ---------------------------------------------------------------------------
# :EstacionMedida -- Gold de trafico / calidad_aire / ruido.
# ---------------------------------------------------------------------------


def fetch_estaciones_trafico(athena_client=None) -> "list[dict]":
    """Un registro por `point_id` con su ubicación más reciente (ventana de
    `_RECENT_WINDOW_DAYS` días), listo para `nodos.estaciones_medida_from_trafico_gold`."""
    sql = f"""
        SELECT point_id,
               max_by(lat, date) AS lat,
               max_by(lon, date) AS lon
        FROM trafico_por_punto_hora
        WHERE {_recent_date_filter()}
        GROUP BY point_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


def fetch_estaciones_calidad_aire(athena_client=None) -> "list[dict]":
    sql = f"""
        SELECT station_id,
               max_by(station_name, date) AS station_name,
               max_by(lat, date) AS lat,
               max_by(lon, date) AS lon
        FROM calidad_aire_por_estacion_contaminante_hora
        WHERE {_recent_date_filter()}
        GROUP BY station_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


def fetch_estaciones_ruido(athena_client=None) -> "list[dict]":
    sql = f"""
        SELECT station_id,
               max_by(station_name, date) AS station_name,
               max_by(lat, date) AS lat,
               max_by(lon, date) AS lon
        FROM ruido_por_estacion_periodo_fecha
        WHERE {_recent_date_filter()}
        GROUP BY station_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


def fetch_estaciones_aforos_peatones_bicicletas(athena_client=None) -> "list[dict]":
    """Un registro por `station_id` con su dirección/distrito y ubicación
    más recientes (tarea 087, Fase A de `doc/086-afluencia-estimada-grafo.md`).

    A diferencia de `trafico`/`calidad_aire`/`ruido`, este Gold
    (`aforos_peatones_bicicletas_por_estacion_modo_hora`, tarea 054) trae
    `location` como columna `struct` anidada (`location.lat`/`location.lon`),
    no columnas planas -- se proyectan como `lat`/`lon` planas en el propio
    SQL para poder reutilizar `_nest_location` sin cambios. `station_id` ya
    es único por estación (las redes de peatones `PERM_PEA##` y de
    bicicletas `PERM_BICI##` usan identificadores propios, ver
    `procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`), así
    que no hace falta agrupar también por `mode` para identificar el nodo."""
    sql = f"""
        SELECT station_id,
               max_by(address, date) AS address,
               max_by(district, date) AS district,
               max_by(location.lat, date) AS lat,
               max_by(location.lon, date) AS lon
        FROM aforos_peatones_bicicletas_por_estacion_modo_hora
        WHERE {_recent_date_filter()}
        GROUP BY station_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


# ---------------------------------------------------------------------------
# :ParadaTransporte -- Gold de transporte_publico_emt / bicimad; Bronze de
# crtm_red_transporte_madrid (ver más abajo).
# ---------------------------------------------------------------------------


def fetch_paradas_emt(athena_client=None) -> "list[dict]":
    """Gold de `transporte_publico_emt` no trae nombre ni ubicación de parada
    (ver `grafo/nodos.py::parada_transporte_from_transporte_publico_emt_gold`)
    -- solo hace falta la identidad (`stop_id`)."""
    sql = f"""
        SELECT DISTINCT stop_id
        FROM transporte_publico_emt_por_parada_hora
        WHERE {_recent_date_filter()}
    """
    return run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)


def fetch_paradas_bicimad(athena_client=None) -> "list[dict]":
    sql = f"""
        SELECT station_id,
               max_by(name, date) AS name,
               max_by(lat, date) AS lat,
               max_by(lon, date) AS lon
        FROM bicimad_por_estacion_hora
        WHERE {_recent_date_filter()}
        GROUP BY station_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


# ---------------------------------------------------------------------------
# :Lugar -- Gold de aparcamientos / cartelera_cines_estrenos; Bronze de
# poi_madrid (ver más abajo).
# ---------------------------------------------------------------------------


def fetch_lugares_aparcamientos(athena_client=None) -> "list[dict]":
    sql = f"""
        SELECT parking_id,
               max_by(name, date) AS name,
               max_by(lat, date) AS lat,
               max_by(lon, date) AS lon
        FROM aparcamientos_por_parking_hora
        WHERE {_recent_date_filter()}
        GROUP BY parking_id
    """
    rows = run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)
    return [_nest_location(row) for row in rows]


def fetch_lugares_cartelera_cines(athena_client=None) -> "list[dict]":
    """Gold de `cartelera_cines_estrenos` no trae coordenadas (ver
    `grafo/nodos.py::lugar_from_cartelera_cines_gold`) -- solo identidad/nombre.

    A fecha de esta tarea, Gold de este dataset sigue vacío (bug ya conocido
    desde la tarea 063: el job Silver->Gold no recibe `--extra-py-files`) --
    esta consulta devuelve `[]` sin ningún error, no es un bug de esta tarea
    (ver docstring del módulo y `grafo/README.md`)."""
    sql = f"""
        SELECT cinema_id,
               max_by(cinema_name, date) AS cinema_name
        FROM cartelera_cines_estrenos_por_pelicula_cine_fecha
        WHERE {_recent_date_filter()}
        GROUP BY cinema_id
    """
    return run_athena_query(sql, GOLD_DATABASE, athena_client=athena_client)


# ---------------------------------------------------------------------------
# Bronze-only (nunca tuvieron Silver/Gold): lectura directa de S3, sin Athena
# (no hay tabla de catálogo para ellas, ver docstring del módulo).
# ---------------------------------------------------------------------------


def _list_bronze_keys(bucket: str, dataset: str, s3_client) -> "list[str]":
    paginator = s3_client.get_paginator("list_objects_v2")
    keys: "list[str]" = []
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{dataset}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".json"):
                keys.append(key)
    return keys


def _read_bronze_records(dataset: str, s3_client=None, bucket: Optional[str] = None) -> "list[dict]":
    """Lee todos los ficheros JSON bajo `<bucket>/<dataset>/` (recorriendo las
    particiones `fecha=/hora=`, mismo layout que
    `ingesta/capturas/bronze.py::BronzeWriter`) y concatena sus registros.

    Devuelve `[]` sin error si no hay ningún objeto bajo ese prefijo -- caso
    real a fecha de esta tarea para los tres orígenes Bronze-only de este
    módulo (ver `grafo/README.md`, "Hallazgo real": `barrios_distritos_madrid`
    /`poi_madrid`/`crtm_red_transporte_madrid` solo se han capturado como
    muestra local en esta sesión, nunca subidos al bucket Bronze real).
    """
    client = s3_client or boto3.client("s3")
    bucket = bucket or BRONZE_BUCKET

    records: "list[dict]" = []
    for key in _list_bronze_keys(bucket, dataset, client):
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        data = json.loads(body)
        if isinstance(data, list):
            records.extend(data)
        else:
            records.append(data)
    return records


def fetch_distritos_bronze(s3_client=None) -> "list[dict]":
    return _read_bronze_records("barrios_distritos_madrid_distritos", s3_client)


def fetch_barrios_bronze(s3_client=None) -> "list[dict]":
    return _read_bronze_records("barrios_distritos_madrid_barrios", s3_client)


def fetch_poi_bronze(s3_client=None) -> "list[dict]":
    return _read_bronze_records("poi_madrid", s3_client)


def fetch_paradas_crtm_bronze(s3_client=None) -> "list[dict]":
    return _read_bronze_records("crtm_red_transporte_madrid", s3_client)


# ---------------------------------------------------------------------------
# Enriquecimiento de :Lugar con POIs de OpenStreetMap (tarea 083): fixture
# local commiteado, no Athena ni S3 (ver docstring de
# `ingesta/capturas/enriquecimiento_osm_lugares.py`).
# ---------------------------------------------------------------------------

OSM_SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "ingesta"
    / "capturas"
    / "samples"
    / "enriquecimiento_osm_lugares_sample.json"
)


def fetch_osm_pois_sample(path: Optional[Path] = None) -> "list[dict]":
    """Lee la muestra ya normalizada de POIs de OpenStreetMap commiteada en
    `ingesta/capturas/samples/enriquecimiento_osm_lugares_sample.json`
    (tarea 083, `ingesta/capturas/enriquecimiento_osm_lugares.py`).

    Se lee el fichero de muestra en vez de repetir la consulta Overpass real
    en cada carga del grafo: la consulta real sobre el bounding box completo
    de Madrid devuelve más de 75.000 nodos (ver docstring del productor) --
    repetirla cada vez que se ejecuta `cargar_grafo.py` no sería un uso
    responsable de una instancia pública gratuita de terceros. Una captura
    real y completa de POIs de OSM (más allá de esta muestra), subida a
    Bronze S3 para que este módulo la lea igual que hace
    `_read_bronze_records` con `poi_madrid`/`crtm_red_transporte_madrid`,
    queda como trabajo futuro deliberado (ver `doc/083-grafo-enriquecimiento-poi-osm.md`)."""
    sample_path = path or OSM_SAMPLE_PATH
    with open(sample_path, encoding="utf-8") as f:
        return json.load(f)
