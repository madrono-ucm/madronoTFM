"""Puerta de calidad Great Expectations del dataset `bicimad` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que `trafico/ge_suite.py`
(tarea 041) y `transporte_publico_emt/ge_suite.py` (tarea 046), ver el
primero para el razonamiento completo de por qué GX valida pero no decide
qué filas pasan a Silver, y por qué corre en el mismo job/`SparkSession` en
vez de en un paso separado (se aplica sin cambios a este dataset, no se
repite aquí).

Cada expectation está anotada con qué regla de `transform.validate_record`
reproduce -- la misma regla de negocio expresada dos veces a propósito (una
testable sin GX, otra declarativa y con informe versionado), ver
`trafico/ge_suite.py` para el motivo completo.

Nota: la comprobación de consistencia `bikes_available + bikes_disabled <=
docks_total` (y su equivalente de anclajes) no tiene una expectation directa
de columna única en GX -- se expresa con `expect_multicolumn_sum_to_equal`
no encaja (no es una igualdad) y GX no tiene una expectation nativa de "suma
de columnas <= columna". Se aproxima creando una columna auxiliar en el
propio DataFrame de Silver antes de validar (ver `glue_bronze_to_silver.py`,
`_with_consistency_columns`) y validando que esa columna auxiliar sea
`<= 0`; documentado aquí para que no parezca una omisión.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

EXPECTATION_SUITE_NAME = "bicimad_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que
    `trafico/ge_suite.py`/`transporte_publico_emt/ge_suite.py`.

    `silver_df` debe incluir las columnas auxiliares `bikes_over_capacity`/
    `docks_over_capacity` que añade `glue_bronze_to_silver.py` antes de
    validar (ver docstring del módulo, arriba).
    """
    datasource = context.sources.add_or_update_spark(name="glue_bicimad_silver")
    data_asset = datasource.add_dataframe_asset(name="bicimad_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "station_id_missing".
    validator.expect_column_values_to_not_be_null("station_id")
    # Reproduce transform.validate_record: "measured_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("measured_at")
    # Reproduce transform.validate_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    # Reproduce transform.validate_record: "*_negative" de cada contador.
    validator.expect_column_values_to_be_between("bikes_available", min_value=0, mostly=1.0)
    validator.expect_column_values_to_be_between("bikes_disabled", min_value=0, mostly=1.0)
    validator.expect_column_values_to_be_between("docks_available", min_value=0, mostly=1.0)
    validator.expect_column_values_to_be_between("docks_disabled", min_value=0, mostly=1.0)
    validator.expect_column_values_to_be_between("docks_total", min_value=0, mostly=1.0)

    # Reproduce transform.validate_record: "bikes_exceed_docks_total" /
    # "docks_exceed_docks_total" (ver docstring del módulo, columnas
    # auxiliares calculadas por glue_bronze_to_silver.py).
    validator.expect_column_values_to_be_between(
        "bikes_over_capacity", max_value=0, mostly=1.0
    )
    validator.expect_column_values_to_be_between(
        "docks_over_capacity", max_value=0, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
