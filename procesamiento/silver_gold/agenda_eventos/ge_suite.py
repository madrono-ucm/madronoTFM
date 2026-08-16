"""Puerta de calidad Great Expectations del dataset `agenda_eventos` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que el resto de `ge_suite.py`
del patrón (`trafico`, tarea 041; ver ese módulo para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver, y por
qué corre en el mismo job/`SparkSession` en vez de en un paso separado).

Cada expectation está anotada con qué regla de `transform.validate_record`
reproduce. `"source_missing_or_unknown"` se reproduce con
`expect_column_values_to_be_in_set` (catálogo cerrado de dos valores, mismo
criterio que `mode` en `aforos_peatones_bicicletas/ge_suite.py`) -- no hace
falta ninguna columna auxiliar de Spark.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

from procesamiento.silver_gold.agenda_eventos.transform import KNOWN_SOURCES

EXPECTATION_SUITE_NAME = "agenda_eventos_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.
    """
    datasource = context.sources.add_or_update_spark(name="glue_agenda_eventos_silver")
    data_asset = datasource.add_dataframe_asset(name="agenda_eventos_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "source_missing_or_unknown".
    validator.expect_column_values_to_be_in_set("source", list(KNOWN_SOURCES))
    # Reproduce transform.validate_record: "event_id_missing".
    validator.expect_column_values_to_not_be_null("event_id")
    # Reproduce transform.validate_record: "title_missing".
    validator.expect_column_values_to_not_be_null("title")
    # Reproduce transform.validate_record: "start_datetime_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("start_datetime")
    # Reproduce transform.validate_record: "captured_at_missing_or_unparseable"
    # (ya renombrado a `ingested_at` en Silver, ver transform.to_silver_record).
    validator.expect_column_values_to_not_be_null("ingested_at")

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
