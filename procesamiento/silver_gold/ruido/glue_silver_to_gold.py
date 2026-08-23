"""Job de AWS Glue: Silver -> Gold del dataset `ruido` (resumen diario por
estación y periodo, más media móvil de 7 días de LAeq).

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` + ventana
correcta a través de múltiples particiones/ficheros de Silver necesita las
primitivas nativas de reduce/window distribuido de Spark, no un
`mapPartitions` fila a fila -- mismo motivo que el resto de datasets del
patrón. `aggregate.py` sigue siendo la fuente de verdad **documental y de
test** de qué agrega Gold (incluida la media móvil de 7 días, ver su
docstring para el razonamiento completo); las expresiones de Spark de este
job están escritas para producir exactamente el mismo esquema de salida que
`aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
otro.

La media móvil usa `Window.rangeBetween` (no `rowsBetween`) sobre
`date_epoch_days` (días desde 1970-01-01, columna numérica auxiliar) para
que la ventana sea de **calendario** (día actual - 6 días hasta día actual),
no de "últimas 7 filas" -- un hueco de fin de semana/festivo (la Red Fija
del SIVCA no publica esos días) reduce cuántos días reales entran en la
ventana en vez de desplazarla, igual que hace `aggregate.py` en Python puro.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
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
from pyspark.sql.window import Window

from procesamiento.silver_gold.incremental import date_range, existing_daily_partitions, today

MADRID_TZ = ZoneInfo("Europe/Madrid")

ROLLING_WINDOW_DAYS = 7


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, `to_date`
    # sobre columnas con componente de hora calcularia en UTC. `measured_date`
    # ya es una fecha pura sin hora (ver transform.py), así que este job en
    # concreto no depende del timezone de sesión para su cálculo actual --
    # se fija de todos modos por consistencia defensiva con el resto del
    # patrón, para que un futuro cambio que añada un `to_timestamp` no
    # reintroduzca el bug en silencio.
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Lectura incremental (tarea 076) -- excepcion explicita al patron del
    # resto del grupo diario (leer solo la particion de Silver de hoy): la
    # media movil de `ROLLING_WINDOW_DAYS` dias necesita, para calcular
    # correctamente la fila de HOY, los `ROLLING_WINDOW_DAYS - 1` dias
    # anteriores como contexto -- leer solo hoy rompería la media (un
    # `Window.rangeBetween` sin las filas anteriores en el DataFrame de
    # entrada simplemente no las encuentra, degradando en silencio a una
    # media de menos de 7 dias). Se leen los ultimos `ROLLING_WINDOW_DAYS`
    # dias (8 con hoy incluido, un dia de margen sobre el minimo estricto de
    # 7) en vez de todo el historico, y luego se filtra la SALIDA a la fila
    # de hoy antes de escribir (ver mas abajo) -- así solo se reescribe una
    # vez cada dia, sin volver a `append`-ear los dias ya calculados en
    # ejecuciones anteriores dentro de la ventana de lectura.
    fechas_ventana = date_range(processed_at, -ROLLING_WINDOW_DAYS, 0)
    s3_client = boto3.client("s3")
    existing_partitions = existing_daily_partitions(s3_client, args["silver_path"], fechas_ventana)
    if not existing_partitions:
        job.commit()
        return

    silver_df = None
    for _fecha, partition_uri in existing_partitions:
        partition_df = spark.read.parquet(partition_uri)
        silver_df = partition_df if silver_df is None else silver_df.unionByName(partition_df)

    # Resumen diario por estación+periodo+día -- ver docstring de
    # `aggregate.py` para el porqué de esta clave (la fuente ya es diaria,
    # no hay ninguna hora que agregar).
    daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
        F.count(F.lit(1)).alias("samples_count"),
        F.first("station_name", ignorenulls=True).alias("station_name"),
        F.first("period_name", ignorenulls=True).alias("period_name"),
        F.first("district", ignorenulls=True).alias("district"),
        F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
        F.avg("laeq_db").alias("avg_laeq_db"),
        F.max("laeq_db").alias("max_laeq_db"),
        F.min("laeq_db").alias("min_laeq_db"),
        F.avg("l1_db").alias("avg_l1_db"),
        F.avg("l10_db").alias("avg_l10_db"),
        F.avg("l50_db").alias("avg_l50_db"),
        F.avg("l90_db").alias("avg_l90_db"),
        F.avg("l99_db").alias("avg_l99_db"),
        F.first("location.lat", ignorenulls=True).alias("lat"),
        F.first("location.lon", ignorenulls=True).alias("lon"),
        F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
    )

    # Columna numérica auxiliar para poder usar `rangeBetween` (ventana de
    # calendario, no de "últimas N filas") -- ver docstring del módulo.
    daily_df = daily_df.withColumn(
        "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
    )

    rolling_window = (
        Window.partitionBy("station_id", "period")
        .orderBy("date_epoch_days")
        .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
    )

    gold_df = (
        daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
        .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
        .drop("date_epoch_days")
        .withColumnRenamed("measured_date", "date")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Se escribe solo la fila de HOY (no toda la ventana de lectura, ver
    # comentario de la lectura incremental arriba): los días anteriores de
    # la ventana ya se escribieron en sus propias ejecuciones -- volver a
    # escribirlos aquí duplicaría filas en Gold en `mode("append")`.
    gold_df_today = gold_df.filter(F.col("date") == today(processed_at))

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # estación, periodo y día, no varias lecturas): particionar solo por
    # `date` es suficiente para podar particiones sin generar ficheros
    # diminutos.
    gold_df_today.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
