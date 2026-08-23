"""Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
`transporte_publico_emt`.

**NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
(tarea 046, arreglado en la tarea 072) calcula internamente una única
hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
reconstruir Silver desde cero. Este script existe únicamente para eso: leer
TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
que cada ejecución histórica del job de producción (antes del arreglo de la
tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
verificado con una consulta Athena real sobre `(stop_id, line, bus_id,
ingested_at)` antes de escribir este script. Se lanza una sola vez a mano
(`aws glue start-job-run`), nunca vía trigger ni schedule.

Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
sobrescribir un prefijo con miles de objetos preexistentes): este script
escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
con la reconstrucción.

Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
de Spark/GX que ya usa el pipeline de producción
(`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
`_write_quality_report`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/transporte_publico_emt/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
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

from procesamiento.silver_gold.transporte_publico_emt.ge_suite import run_quality_report
from procesamiento.silver_gold.transporte_publico_emt.glue_bronze_to_silver import (
    SILVER_SCHEMA,
    _process_partition,
    _write_quality_report,
)

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
    # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
    # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
    # con la hora de Madrid real de `ingested_at`.
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Bronze de una vez -- exactamente lo que necesita una
    # reconstrucción completa.
    bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)

    # La deduplicación real que faltaba: reprocesar el mismo histórico de
    # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
    # registro repetido decenas de veces. Un cuarteto (stop_id, line, bus_id,
    # ingested_at) identifica de forma única una estimación de llegada real
    # de un mismo lote de ingesta.
    silver_df = silver_df.dropDuplicates(["stop_id", "line", "bus_id", "ingested_at"])
    silver_df.cache()

    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"transporte_publico_emt_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
    # hora de Madrid).
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))

    # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
    # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
    # sustituto de ese borrado previo.
    silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
