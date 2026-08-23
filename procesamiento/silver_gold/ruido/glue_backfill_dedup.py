"""Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
`ruido` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).

**No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
(tarea 053, arreglado en la tarea 076) lee solo la partición Bronze del día
de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
histórico", así que no sirve para reconstruir Silver desde cero. Este script
existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
Athena real (ver `doc/077-...md`): `n=6` para el mismo
(`station_id`, `period`, `measured_date`).

Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).

`(station_id, period, measured_date)` es la clave natural del dataset (misma
clave que agrupa `aggregate.py` para el resumen diario -- ver
`glue_silver_to_gold.py`, "Resumen diario por estación+periodo+día").

Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
`SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
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

from procesamiento.silver_gold.ruido.glue_bronze_to_silver import (
    SILVER_SCHEMA,
    _process_partition,
    _write_quality_report,
)
from procesamiento.silver_gold.ruido.ge_suite import run_quality_report

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

    # La deduplicación real que faltaba. Clave natural: estación + periodo
    # (D/E/T/N) + día medido -- misma clave que agrupa `aggregate.py`.
    silver_df = silver_df.dropDuplicates(["station_id", "period", "measured_date"])
    silver_df.cache()

    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"ruido_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Partición solo por `fecha` (derivada de `measured_date`), igual que el
    # pipeline de producción -- esta fuente es diaria, sin hora real.
    silver_partitioned = silver_df.withColumn("fecha", silver_df["measured_date"])

    # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo.
    silver_partitioned.write.mode("overwrite").partitionBy("fecha").parquet(args["silver_path"])

    job.commit()


if __name__ == "__main__":
    main()
