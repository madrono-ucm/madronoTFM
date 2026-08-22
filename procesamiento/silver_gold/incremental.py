"""Helpers de lectura incremental para los jobs de Glue Bronze->Silver/
Silver->Gold (tarea 072).

## El bug que arregla este módulo

Hasta esta tarea, los 28 jobs (`glue_bronze_to_silver.py`/
`glue_silver_to_gold.py` de los 14 datasets) leían siempre la **raíz**
completa de su dataset de origen (`spark.read...json(args["bronze_path"])`/
`spark.read.parquet(args["silver_path"])`), sin ningún filtro de fecha/hora.
Como Bronze crece sin parar (ingesta continua cada 5-15 min desde hace
días), cada ejecución reprocesaba **todo el histórico acumulado**, no solo
los datos nuevos desde la última vez -- una trayectoria de coste de Glue
creciente sin límite (factura real de 39,71 USD, ver
`doc/072-arreglo-lectura-incremental-glue.md` para el diagnóstico completo).

Las funciones de aquí calculan, en Python puro (sin `pyspark` ni `boto3` en
las de cómputo de fecha/ruta, para poder testear sin Spark instalado, igual
que el resto de `procesamiento/`), qué partición(es) Hive
(`fecha=.../hora=.../`) tocan en cada ejecución según el instante en que
corre el job -- y una única función que sí toca red (`partition_has_objects`,
con un cliente S3 inyectable) para no fallar cuando esa partición está
vacía (p.ej. la primera vez que corre tras esta tarea, o un hueco real de
ingesta).

## Por qué el cálculo es por reloj (`datetime.now`), no por bookmark de Glue

AWS Glue Job Bookmarks (`--job-bookmark-option`) es el mecanismo nativo para
"procesar solo lo nuevo desde la última vez", pero **ya está deshabilitado
a propósito** en los 28 jobs (`"--job-bookmark-option" = "job-bookmark-
disable"`, ver `glue.tf`) y activarlo ahora habría significado que la
*primera* ejecución con bookmarks tuviese que recorrer igualmente todo el
histórico ya acumulado antes de poder empezar a ser incremental -- exactamente
la ejecución cara que esta tarea necesita evitar desde ya, dado la urgencia
real del coste. Calcular la partición a partir del reloj (la hora/día en que
dispara el trigger `SCHEDULED`/`CONDITIONAL`, ver `glue_scheduling.tf`) es
barato desde la primera ejecución, sin ningún histórico que recorrer antes.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def previous_hour(moment: datetime) -> "tuple[str, str]":
    """`(fecha, hora)` de la hora completa inmediatamente anterior a `moment`.

    Usado por los 6 datasets de cadencia horaria (`trafico`,
    `transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
    `meteorologia`): su trigger `SCHEDULED` dispara en el minuto 10 de cada
    hora (`glue_trigger_hourly_schedule`, `glue_scheduling.tf`), momento en
    el que la partición de la hora **anterior** ya está completa (el
    productor más lento del grupo, `aparcamientos`, ingesta cada 15 min) --
    la de la hora en curso, en cambio, todavía está incompleta.
    """
    target = moment - timedelta(hours=1)
    return f"{target:%Y-%m-%d}", f"{target:%H}"


def date_range(moment: datetime, start_offset_days: int, end_offset_days: int) -> "list[str]":
    """Fechas (`yyyy-MM-dd`) desde `moment + start_offset_days` hasta
    `moment + end_offset_days` días, ambos extremos incluidos, en orden
    cronológico. `start_offset_days`/`end_offset_days` pueden ser negativos
    (pasado) o positivos (futuro) -- p.ej. `date_range(moment, 0, 4)` para
    la previsión de `cams_calidad_aire` (hoy hasta hoy+4, su horizonte real
    de 96h), o `date_range(moment, -7, -1)` para la ventana de 7 días de la
    media móvil de `ruido` (ayer hacia atrás, ver docstring de
    `ruido/aggregate.py`).
    """
    return [
        f"{(moment + timedelta(days=offset)):%Y-%m-%d}"
        for offset in range(start_offset_days, end_offset_days + 1)
    ]


def today(moment: datetime) -> str:
    """Fecha (`yyyy-MM-dd`) de `moment`, para los datasets de cadencia diaria
    cuyo contenido coincide con el día de ingesta (ver
    `doc/072-arreglo-lectura-incremental-glue.md` para el detalle de qué
    dataset usa esta función frente a `date_range`)."""
    return date_range(moment, 0, 0)[0]


def hourly_partition_uri(base_path: str, fecha: str, hora: str) -> str:
    """URI/ruta `<base_path>/fecha=<fecha>/hora=<hora>/`."""
    return f"{base_path.rstrip('/')}/fecha={fecha}/hora={hora}/"


def daily_partition_uri(base_path: str, fecha: str) -> str:
    """URI/ruta `<base_path>/fecha=<fecha>/` (todas las horas de ese día)."""
    return f"{base_path.rstrip('/')}/fecha={fecha}/"


def partition_has_objects(s3_client, uri: str) -> bool:
    """`True` si `uri` (un prefijo `s3://bucket/prefijo/`) tiene al menos un
    objeto real. `s3_client` es inyectable (un cliente `boto3` real en
    producción, un doble de test en `procesamiento/tests/`) para no
    depender de credenciales/red reales en los tests.
    """
    bucket, _, prefix = uri.removeprefix("s3://").partition("/")
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    return response.get("KeyCount", 0) > 0


def existing_daily_partitions(s3_client, base_path: str, fechas: "list[str]") -> "list[tuple[str, str]]":
    """Subconjunto de `fechas` (con su URI) que realmente tienen objetos bajo
    `base_path`, en el mismo orden que `fechas`. Usado por los jobs
    Silver->Gold que necesitan leer una ventana de varios días (ver
    `date_range`): algunos de esos días pueden no existir todavía (el
    dataset lleva menos días en producción que el tamaño de la ventana) o
    nunca (huecos reales de ingesta) -- pasarlos igualmente a
    `spark.read.parquet(...)` fallaría con "Path does not exist".
    """
    result = []
    for fecha in fechas:
        uri = daily_partition_uri(base_path, fecha)
        if partition_has_objects(s3_client, uri):
            result.append((fecha, uri))
    return result
