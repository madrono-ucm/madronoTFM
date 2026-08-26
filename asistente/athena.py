"""Consulta a Athena (capa Gold) para las `tools` del agente MCP de Madroño.

Mismo patrón que `grafo/extract.py` (tarea 069: `boto3` +
`start_query_execution`/`get_query_execution`/`get_query_results` sobre el
workgroup `madrono-tfm-dev-silver-gold`, con el mismo bucle de sondeo con
backoff corto). No se importa `grafo.extract` directamente -- mismo criterio
ya aplicado en `asistente/timeutils.py` respecto a `ingesta/`: mantener
`asistente/` autocontenido y desplegable de forma independiente del resto
del monorepo, en vez de acoplarlo a un paquete hermano.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import boto3

ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "madrono-tfm-dev-silver-gold")
GOLD_DATABASE = os.environ.get("ATHENA_GOLD_DATABASE", "madrono-tfm_dev_gold")
# Tarea 093: `eventos_cercanos` lee Silver directamente, no Gold -- Gold de
# `agenda_eventos` agrega por categoría/distrito/fecha (sin lat/lon por
# evento individual, ver doc/093-...md), la única fuente con posición real
# por evento es Silver.
SILVER_DATABASE = os.environ.get("ATHENA_SILVER_DATABASE", "madrono-tfm_dev_silver")

_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}
_INTEGER_TYPES = {"tinyint", "smallint", "integer", "int", "bigint"}
_FLOAT_TYPES = {"float", "double", "decimal", "real"}


def sql_literal(value: str) -> str:
    """Escapa `value` para insertarlo como literal de texto SQL (comillas
    simples duplicadas, convención estándar). Suficiente aquí porque `value`
    solo se usa dentro de un `LIKE`/`=`, nunca como identificador de columna
    o tabla -- no hace falta la API de "prepared statements" de Athena (más
    pesada) para una consulta puntual como esta."""
    return value.replace("'", "''")


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
    y espera el resultado con un bucle de sondeo de backoff corto (mismo
    patrón que `grafo/extract.py::run_athena_query`, ver doc/066/069).

    `athena_client` es inyectable (por defecto, `boto3.client("athena")`)
    para poder testear el parseo sin credenciales/conexión real -- ver
    `asistente/tests/test_mcp_tools.py`.
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
