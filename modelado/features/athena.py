"""Consulta a Athena para el feature store (ML_01).

`run_athena_query` (reutilizado de `grafo.extract`) pagina el resultado con
`get_query_results` a 1000 filas por llamada -- bien para las consultas
puntuales del asistente/grafo (decenas o cientos de filas), inviable para el
feature store (el panel de tráfico son ~1,5 M filas -> ~1500 round-trips a
la API, ~15 min).

`query_df` usa en su lugar el **CSV que Athena deja en S3**
(`ResultConfiguration.OutputLocation`) y lo lee de una vez con
`pandas.read_csv`. A diferencia de `asistente/athena.py` -- que copia el
helper para desplegarse como servicio --, `modelado/` corre como batch en el
mismo repo/entorno, así que acoplarse a `grafo.extract` para lanzar/esperar
la consulta es correcto.
"""

from __future__ import annotations

import boto3

from grafo.extract import GOLD_DATABASE, run_athena_query

__all__ = ["GOLD_DATABASE", "run_athena_query", "query_df"]

_ATHENA_WORKGROUP = "madrono-tfm-dev-silver-gold"


def query_df(sql: str, database: str = GOLD_DATABASE, *, athena_client=None):
    """Lanza `sql`, espera a que termine, y lee el CSV de resultado
    directamente de S3 -> `pandas.DataFrame`. Para result sets grandes es
    órdenes de magnitud más rápido que paginar `get_query_results`.

    `athena_client` inyectable para test (con un fake que exponga
    `start_query_execution`/`get_query_execution`); si se pasa uno de test se
    cae al camino de `run_athena_query` (paginado) para no requerir S3.
    """
    import pandas as pd

    if athena_client is not None:
        return pd.DataFrame(run_athena_query(sql, database, athena_client=athena_client))

    athena = boto3.client("athena")
    exec_id = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=_ATHENA_WORKGROUP,
    )["QueryExecutionId"]

    import time

    while True:
        ex = athena.get_query_execution(QueryExecutionId=exec_id)["QueryExecution"]
        state = ex["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.0)
    if state != "SUCCEEDED":
        reason = ex["Status"].get("StateChangeReason", "sin motivo")
        raise RuntimeError(f"Athena {exec_id} terminó en {state}: {reason}")

    out_uri = ex["ResultConfiguration"]["OutputLocation"]  # s3://bucket/key.csv
    bucket, key = out_uri[len("s3://"):].split("/", 1)
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
    return pd.read_csv(body)
