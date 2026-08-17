"""Puerta de calidad Great Expectations del dataset `afluencia_lugares` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que el resto de `ge_suite.py`
del patrón (`trafico`, tarea 041; ver ese módulo para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver).

Cada expectation está anotada con qué regla de `transform.validate_record`
reproduce.

Nota: `typical_by_hour` no tiene una expectation nativa de "cada valor de
cada array anidado de un struct está en un rango" -- se aproxima igual que
`calidad_aire`/`meteorologia`/`cams_calidad_aire`: dos columnas auxiliares
(`typical_by_hour_min_value`/`typical_by_hour_max_value`) calculadas en
`glue_bronze_to_silver.py` antes de validar (aplanando los 7 arrays del
struct `typical_by_hour` y tomando su mínimo/máximo), comprobadas aquí como
`>= 0`/`<= 100`. Ambas columnas son `null` para un registro sin
`typical_by_hour` (lugar sin patrón habitual, ver `transform.py`) -- GX
ignora los valores `null` en `expect_column_values_to_be_between` por
defecto, igual que ya hace con `live_pct` en este mismo módulo.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

EXPECTATION_SUITE_NAME = "afluencia_lugares_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.

    `silver_df` debe incluir las columnas auxiliares
    `typical_by_hour_min_value`/`typical_by_hour_max_value` que añade
    `glue_bronze_to_silver.py` antes de validar (ver docstring del módulo,
    arriba).
    """
    datasource = context.sources.add_or_update_spark(name="glue_afluencia_lugares_silver")
    data_asset = datasource.add_dataframe_asset(name="afluencia_lugares_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "place_id_missing".
    validator.expect_column_values_to_not_be_null("place_id")
    # Reproduce transform.validate_record: "name_missing".
    validator.expect_column_values_to_not_be_null("name")
    # Reproduce transform.validate_record: "captured_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    # Reproduce transform.validate_record: "live_pct_out_of_range".
    # `live_pct` puede ser null (dato válido, ver transform.py) -- GX
    # ignora los null en esta expectation por defecto.
    validator.expect_column_values_to_be_between("live_pct", min_value=0, max_value=100, mostly=1.0)

    # Reproduce transform.validate_record: "typical_by_hour_value_out_of_range"
    # (columnas auxiliares, ver docstring del módulo).
    validator.expect_column_values_to_be_between(
        "typical_by_hour_min_value", min_value=0, mostly=1.0
    )
    validator.expect_column_values_to_be_between(
        "typical_by_hour_max_value", max_value=100, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
