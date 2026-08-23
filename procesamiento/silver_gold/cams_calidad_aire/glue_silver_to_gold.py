"""Job de AWS Glue: Silver -> Gold del dataset `cams_calidad_aire` (valor
medio/máximo previsto por contaminante y día que predicen).

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
través de múltiples particiones/ficheros de Silver necesita las primitivas
nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
expresiones de Spark de este job están escritas para producir exactamente el
mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
en uno debe reflejarse en el otro.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
    # `date_format(to_timestamp(...), ...)` de mas abajo calcularia en UTC,
    # desalineado con `today()` (Python, Europe/Madrid).
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
    # nunca la raiz completa del dataset -- mismo motivo de coste que
    # Bronze->Silver (tarea 072). `fecha` en Silver es la del instante
    # **previsto** (`valid_datetime`, ver glue_bronze_to_silver.py), que
    # puede caer varios dias en el futuro respecto al dia de ingestion (CAMS
    # predice hasta 96h/4 dias vista) -- pero Silver es un almacen
    # persistente: cada particion `fecha=<dia>` recibe escrituras de varias
    # corridas de prevision distintas mientras ese dia sigue dentro del
    # horizonte, y esta lectura la visita una unica vez, el dia en que ese
    # dia de calendario se convierte en "hoy" (momento en que ya contiene
    # todas las corridas que llegaron a predecirlo).
    fecha = today(processed_at)
    silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
    if not partition_has_objects(boto3.client("s3"), silver_partition_path):
        job.commit()
        return

    silver_df = spark.read.parquet(silver_partition_path)

    # `fecha_validez` = día del instante previsto (`valid_datetime`), no el
    # horizonte de antelación (`leadtime_hour`) ni el día de la corrida
    # (`forecast_issued_at`) -- mismo criterio que `aggregate.py`.
    silver_with_fecha_validez = silver_df.withColumn(
        "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
    )

    gold_df = (
        silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
        .agg(
            F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
            F.first("unit", ignorenulls=True).alias("unit"),
            F.count(F.lit(1)).alias("samples_count"),
            F.avg("value").alias("avg_value"),
            F.max("value").alias("max_value"),
            F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
            F.min("forecast_issued_at").alias("first_forecast_issued_at"),
            F.max("forecast_issued_at").alias("last_forecast_issued_at"),
        )
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es mucho más pequeño que Silver (una fila por contaminante y día
    # previsto, no por hora/corrida): particionar por `pollutant` basta para
    # podar particiones sin generar ficheros diminutos -- el número de
    # contaminantes es reducido, a diferencia de particionar por
    # `fecha_validez` (menos selectivo aquí: cada corrida diaria predice
    # varios días de horizonte para todos los contaminantes a la vez).
    gold_df.write.mode("append").partitionBy("pollutant").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
