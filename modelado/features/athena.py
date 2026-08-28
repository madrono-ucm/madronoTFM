"""Consulta a Athena para el feature store (ML_01).

Reutiliza el helper ya probado de `grafo.extract` (tarea 069: `boto3` +
`start_query_execution`/`get_query_results` sobre el workgroup
`madrono-tfm-dev-silver-gold`, con sondeo de backoff corto y casteo de tipos
según `ResultSetMetadata`). A diferencia de `asistente/athena.py` -- que
copia el helper para poder desplegarse como servicio independiente --,
`modelado/` corre como batch/cuadernos en el mismo repo y entorno, así que
acoplarse a `grafo.extract` es correcto y evita una tercera copia.
"""

from __future__ import annotations

from grafo.extract import GOLD_DATABASE, run_athena_query

__all__ = ["GOLD_DATABASE", "run_athena_query", "query_df"]


def query_df(sql: str, database: str = GOLD_DATABASE, *, athena_client=None):
    """`run_athena_query` -> `pandas.DataFrame`. Import perezoso de pandas
    para que importar este módulo no lo exija (los tests de `panel.py` sí lo
    necesitan; una consulta puntual desde un cuaderno también)."""
    import pandas as pd

    return pd.DataFrame(run_athena_query(sql, database, athena_client=athena_client))
