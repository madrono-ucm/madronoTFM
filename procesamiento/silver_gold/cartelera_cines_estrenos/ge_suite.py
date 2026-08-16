"""Puerta de calidad Great Expectations del dataset `cartelera_cines_estrenos`
(Silver).

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
reproduce. Dos de las reglas de `validate_record` no tienen ninguna
expectation equivalente aquí a propósito:

- `"not_a_screening_session"` (registros de estreno semanal, ver
  `transform.py`): esos registros nunca llegan a Silver -- no hay ninguna
  columna `record_type` en el esquema de Silver de este dataset que una
  expectation pudiera comprobar (no es una regla de rango/nulidad sobre un
  campo, es un filtro de qué *tipo* de registro entra en este subpaquete).
- `"showtime_already_passed"` (`showtime_datetime < ingested_at`): se
  reproduce con `expect_column_pair_values_a_to_be_greater_than_b`, la
  única expectation nativa de GX para comparar dos columnas entre sí --
  como Silver guarda ambas marcas de tiempo como cadenas ISO-8601 (no como
  `TimestampType`, mismo criterio que el resto del patrón), la comparación
  es **lexicográfica**, no una comparación de instantes real. Esto es una
  aproximación válida solo porque ambos campos comparten formato y usan el
  mismo desfase horario local (Europe/Madrid, ver
  `ingesta/capturas/bronze.py`); un cambio de horario de verano a invierno
  entre `showtime_datetime` e `ingested_at` de un mismo registro
  (`+02:00` vs `+01:00`) podría, en un caso límite, romper el orden
  lexicográfico -- aceptable aquí porque esta expectation es solo
  observabilidad/auditoría (no decide qué filas llegan a Silver, ver
  docstring de `transform.py`: eso ya lo hizo `validate_record`, con
  comparación real de objetos `datetime`).
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

EXPECTATION_SUITE_NAME = "cartelera_cines_estrenos_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.
    """
    datasource = context.sources.add_or_update_spark(name="glue_cartelera_cines_estrenos_silver")
    data_asset = datasource.add_dataframe_asset(name="cartelera_cines_estrenos_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "movie_title_missing".
    validator.expect_column_values_to_not_be_null("movie_title")
    # Reproduce transform.validate_record: "cinema_id_missing".
    validator.expect_column_values_to_not_be_null("cinema_id")
    # Reproduce transform.validate_record: "showtime_id_missing".
    validator.expect_column_values_to_not_be_null("showtime_id")
    # Reproduce transform.validate_record: "showtime_datetime_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("showtime_datetime")
    # Reproduce transform.validate_record: "captured_at_missing_or_unparseable"
    # (ya renombrado a `ingested_at` en Silver, ver transform.to_silver_record).
    validator.expect_column_values_to_not_be_null("ingested_at")
    # Reproduce transform.validate_record: "showtime_already_passed" -- ver
    # docstring del módulo para la limitación de la comparación lexicográfica.
    validator.expect_column_pair_values_a_to_be_greater_than_b(
        column_A="showtime_datetime", column_B="ingested_at", or_equal=True, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
