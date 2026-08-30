"""Job de AWS Glue: Silver -> Gold del dataset `aemet_prevision_avisos`.

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

Un único job produce **las dos** tablas Gold (previsión por municipio y
horizonte, avisos por zona/día/nivel), mismo motivo que
`glue_bronze_to_silver.py` ("job de Glue x2" pedido por el enunciado, no
cuatro jobs).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
través de múltiples particiones/ficheros de Silver necesita las primitivas
nativas de reduce distribuido de Spark, no un cálculo fila a fila -- mismo
motivo que el resto de datasets del patrón. `aggregate.py` sigue siendo la
fuente de verdad **documental y de test** de qué agrega Gold; las
expresiones de Spark de este job están escritas para producir exactamente
el mismo esquema de salida que
`aggregate.aggregate_prevision_silver_to_gold`/
`aggregate.aggregate_avisos_silver_to_gold`; un cambio en uno debe
reflejarse en el otro.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de origen.
- `gold_prevision_path` / `gold_avisos_path`: prefijos S3 de destino, p.ej.
  `.../aemet_prevision_por_municipio_leadtime/` /
  `.../aemet_avisos_por_zona_fecha_nivel/`.
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

from procesamiento.silver_gold.incremental import partition_has_objects

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "silver_prevision_path",
            "silver_avisos_path",
            "gold_prevision_path",
            "gold_avisos_path",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
    # `to_timestamp`/`date_format`/`to_date` de mas abajo calcularian en UTC,
    # desalineado con `today()` (Python, Europe/Madrid).
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    # FIL_11: sobrescritura dinamica de particiones -- `mode("overwrite")`
    # reemplaza solo las particiones presentes en el DataFrame, sin borrar
    # las demas. La usa la rama de avisos (recalculo idempotente por `fecha`);
    # para prevision (recalculo completo, 1 municipio) el efecto es el mismo
    # que la sobrescritura estatica.
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # --- Previsión: (municipio_code, leadtime_days) -------------------------
    #
    # A diferencia del resto del patrón (tarea 076), este flujo NO se puede
    # acotar a la partición de Silver de hoy: `leadtime_days` (el horizonte,
    # p.ej. "mañana" = 1) agrupa a propósito previsiones de MUCHOS días de
    # calendario distintos capturadas en momentos distintos -- ver docstring
    # de `aggregate.py`, "Un mismo leadtime_days agrupa previsiones de días
    # de calendario distintos". La clave de negocio no incluye ninguna
    # fecha, así que cada ejecución necesita el histórico completo de Silver
    # para recalcular correctamente cada horizonte -- leer solo hoy dejaría
    # cada bucket con una única captura en vez de con todo su histórico.
    # El volumen de este dataset es pequeño (una previsión de 7 días para un
    # único municipio, una vez al día -> unas 2500 filas/año), así que leer
    # todo el histórico sigue siendo barato incluso tras meses de
    # acumulación: el problema real de coste que motivó esta serie de tareas
    # (072-076) no aplica aquí igual que a `trafico`/`bicimad` (ingesta cada
    # pocos minutos). El problema real para ESTE dataset era otro: escribir
    # con `mode("append")` duplicaba la fila de cada horizonte en cada
    # ejecución (una fila más por (municipio_code, leadtime_days) cada día,
    # creciendo sin límite) en vez de mantener una única fila por horizonte
    # -- se sustituye por `mode("overwrite")` (recálculo completo cada vez,
    # sin acotar particiones -- Gold de previsión no está particionado por
    # fecha, ver docstring del módulo).
    silver_prevision_df = spark.read.parquet(args["silver_prevision_path"])

    prevision_with_leadtime = silver_prevision_df.withColumn(
        "leadtime_days",
        F.datediff(F.to_date("valid_date"), F.to_date("ingested_at")),
    )

    gold_prevision_df = (
        prevision_with_leadtime.groupBy("municipio_code", "leadtime_days")
        .agg(
            F.first("municipio_name", ignorenulls=True).alias("municipio_name"),
            F.count(F.lit(1)).alias("samples_count"),
            F.avg("temperature_max_c").alias("avg_temperature_max_c"),
            F.max("temperature_max_c").alias("max_temperature_max_c"),
            F.avg("temperature_min_c").alias("avg_temperature_min_c"),
            F.min("temperature_min_c").alias("min_temperature_min_c"),
            F.avg("precipitation_probability_pct").alias("avg_precipitation_probability_pct"),
            F.max("precipitation_probability_pct").alias("max_precipitation_probability_pct"),
            F.min("valid_date").alias("first_valid_date"),
            F.max("valid_date").alias("last_valid_date"),
        )
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es mucho más pequeño que Silver: particionar por `municipio_code`
    # basta para podar particiones sin generar ficheros diminutos -- el
    # número de municipios/horizontes es reducido, a diferencia de
    # particionar por fecha (que aquí no tiene sentido: cada fila agrega
    # muchos días de calendario distintos, ver docstring de `aggregate.py`).
    # `mode("overwrite")` (no `"append"`, ver comentario arriba): cada
    # ejecución sustituye Gold entero por el recálculo completo, en vez de
    # acumular una fila nueva por horizonte cada día.
    gold_prevision_df.write.mode("overwrite").partitionBy("municipio_code").parquet(args["gold_prevision_path"])

    # --- Avisos: (zone, fecha, level) ---------------------------------------
    #
    # FIL_11: antes se leía solo `Silver/aemet_avisos/fecha=hoy` y se
    # `append`-eaba. Dos fallos: (1) Silver-avisos se particiona por el día
    # de `effective_from` (ver `glue_bronze_to_silver.py`), que para un aviso
    # emitido hoy suele ser un día **futuro** -> `fecha=hoy` casi nunca tenía
    # objetos y toda la rama se saltaba en silencio (Gold congelado); (2)
    # `mode("append")` duplicaba filas al reprocesar un día (Gold llegó a
    # tener 4x la misma `(zone, fecha, level)`). El volumen de avisos es
    # minúsculo (unos pocos al día, particiones de ~7 KB), así que se lee la
    # **raíz completa** de Silver-avisos y se reescribe Gold con
    # sobrescritura dinámica de particiones (`partitionOverwriteMode=dynamic`,
    # fijado en `main()`): cada ejecución recalcula todas las particiones
    # `fecha=` y las reemplaza, sin duplicar y recogiendo cualquier aviso
    # amarillo/naranja/rojo sea cual sea su fecha de vigencia. Coincide con
    # `aggregate.aggregate_avisos_silver_to_gold`, que nunca filtró por "hoy".
    if partition_has_objects(boto3.client("s3"), args["silver_avisos_path"]):
        silver_avisos_df = spark.read.parquet(args["silver_avisos_path"])

        avisos_with_fecha = silver_avisos_df.withColumn(
            "fecha", F.date_format(F.to_timestamp("effective_from"), "yyyy-MM-dd")
        )

        gold_avisos_df = (
            avisos_with_fecha.groupBy("zone", "fecha", "level")
            .agg(
                F.count(F.lit(1)).alias("samples_count"),
                F.countDistinct("identifier").alias("alerts_count"),
                F.sort_array(F.collect_set("phenomenon")).alias("phenomena"),
                F.min("effective_from").alias("first_effective_from"),
                F.max("effective_until").alias("last_effective_until"),
            )
            .withColumn("schema_version", F.lit(1))
            .withColumn("processed_at", F.lit(processed_at.isoformat()))
        )

        gold_avisos_df.write.mode("overwrite").partitionBy("fecha").parquet(args["gold_avisos_path"])

    job.commit()


if __name__ == "__main__":
    main()
