"""FIL_83/VIC_43 -- la caché TTL de `asistente.athena.run_athena_query` y
`asistente.neo4j_client.run_neo4j_query` vive en un `store` de módulo, fuera
del ciclo de vida de cualquier test. En el proceso normal de la suite
(`ASSISTANT_CACHE_TTL` sin definir -> caché desactivada) esto es invisible.
Pero con la variable puesta a un valor real -- como hace el despliegue
(`ASSISTANT_CACHE_TTL=900`, ver `infra/OPERACION.md`) -- dos tests distintos
que generan el mismo texto de SQL/Cypher pero con datos falsos distintos
(`FakeAthenaClient`/`FakeNeo4jDriver` no forman parte de la clave de caché,
a propósito, ver `asistente/cache.py::_clave`) pueden leer el resultado
cacheado de otro test en vez de ejecutar su propio *fake*: confirmado el
2026-09-10 (`VIC_43`), 17 tests de `asistente/tests/test_mcp_tools.py` y
`test_opciones_movilidad.py` fallan así al forzar
`ASSISTANT_CACHE_TTL=900` en la suite completa, pero pasan uno a uno.

Este fixture limpia ambas cachés antes de cada test para que la suite sea
determinista con cualquier valor de `ASSISTANT_CACHE_TTL` -- no solo con el
`0` por defecto.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _limpiar_caches_del_asistente():
    from asistente.athena import run_athena_query
    from asistente.neo4j_client import run_neo4j_query

    run_athena_query.cache_clear()
    run_neo4j_query.cache_clear()
    yield
    run_athena_query.cache_clear()
    run_neo4j_query.cache_clear()
