"""Lectura de secretos desde SSM Parameter Store en runtime (`FIL_17`).

Antes, las Lambda de productores recibían el valor real de cada credencial
como variable de entorno **en claro** (visible en la consola y en
`aws lambda get-function-configuration`). Ahora `infra/terraform/lambda.tf`
inyecta sólo el **path** del parámetro SSM (`<NOMBRE>_SSM_PATH`) y este
helper resuelve el valor con `ssm:GetParameter` `--with-decryption` una sola
vez por *cold start* del contenedor (cacheado a nivel de módulo).

`get_secret("AEMET_API_KEY")`:

1. Si `AEMET_API_KEY_SSM_PATH` está en el entorno → lee ese parámetro de SSM
   (cacheado por path).
2. Si no, cae a `os.environ.get("AEMET_API_KEY")` — así los tests, el uso
   por CLI en local y cualquier despliegue que todavía inyecte el valor
   directo siguen funcionando sin cambios.
3. Si ninguno de los dos está → `None`.

Un error de SSM cuando el path SÍ está configurado se propaga (no se
silencia): si el operador ha pedido SSM, un fallo debe ser ruidoso, no
degradar a "sin credencial".
"""

from __future__ import annotations

import os

_cache: "dict[str, str]" = {}


def _fetch_from_ssm(path: str) -> str:
    if path not in _cache:
        import boto3

        resp = boto3.client("ssm").get_parameter(Name=path, WithDecryption=True)
        _cache[path] = resp["Parameter"]["Value"]
    return _cache[path]


def get_secret(name: str) -> "str | None":
    """Valor del secreto lógico `name` (p. ej. `"AEMET_API_KEY"`).

    Prioriza el path SSM en `<name>_SSM_PATH`; si no, el valor directo en
    `<name>`; si ninguno, `None`.
    """
    path = os.environ.get(f"{name}_SSM_PATH")
    if path:
        return _fetch_from_ssm(path)
    return os.environ.get(name)


def clear_cache() -> None:
    """Vacía la caché de parámetros SSM (para tests)."""
    _cache.clear()
