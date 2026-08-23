"""Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
`aforos_peatones_bicicletas` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).

**No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
(tarea 054, arreglado en la tarea 076) lee solo la partición Bronze del día
de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
histórico", así que no sirve para reconstruir Silver desde cero. Este script
existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
todo el histórico acumulado en vez de solo el día nuevo -- confirmado en esta
tarea con un análisis directo de los 144 ficheros parquet de Silver (la
tabla de Glue Catalog tiene `partition projection` con rango `fecha` desde
2026-08-01, que excluye el dato real de 2024-06-29/06-30 -- Athena no sirve
para verificar este dataset en concreto, ver `doc/077-...md`): `n=6` para el
mismo (`station_id`, `mode`, `measured_at`) -- exactamente las 6 ejecuciones
históricas que reescribieron el CSV completo de un año de golpe cada vez.

Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).

`(station_id, mode, measured_at)` es la clave natural del dataset (`mode`
distingue las dos redes de estaciones -- peatones/bicicletas -- que
comparten el mismo campo `count`, ver docstring de `transform.py`, "parte de
la clave natural de agregación en `aggregate.py`").

Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
`SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
- `quality_report_path`: prefijo S3 donde se escribe el informe de
  validación de Great Expectations (un JSON, igual que el pipeline de
  producción).
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import great_expectations as gx
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import date_format, to_timestamp

from procesamiento.silver_gold.aforos_peatones_bicicletas.glue_bronze_to_silver import (
    SILVER_SCHEMA,
    _process_partition,
    _write_quality_report,
)
from procesamiento.silver_gold.aforos_peatones_bicicletas.ge_suite import run_quality_report

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Bronze de una vez.
    bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)

    # La deduplicación real que faltaba: reprocesar el mismo CSV histórico
    # completo en cada ejecución dejó hasta 6 copias de cada fila. Clave
    # natural: estación + red (peatones/bicicletas) + instante medido.
    silver_df = silver_df.dropDuplicates(["station_id", "mode", "measured_at"])
    silver_df.cache()

    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"aforos_peatones_bicicletas_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Mismo esquema de partición que Bronze (fecha=/hora=, derivado de
    # `measured_at`), igual que el pipeline de producción.
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))

    # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo.
    silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
