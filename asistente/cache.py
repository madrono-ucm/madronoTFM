"""Caché TTL en proceso para las rutas de lectura calientes del asistente
(`FIL_83`).

Cada llamada a una tool va en frío a Athena/Neo4j. Con el pipeline de datos
**congelado desde 2026-08-30**, el resultado de una consulta Gold no cambia,
así que un TTL generoso es seguro y recorta latencia + coste de escaneo.

Diseño:

- `@cacheado(ttl_s=...)` envuelve una función pura-ish (mismos args → mismo
  resultado durante `ttl_s`). Clave = repr normalizado de `(args, kwargs)`.
- LRU con cota (`maxsize`) para no crecer sin límite.
- **Desactivada por defecto** (`ASSISTANT_CACHE_TTL=0`): así la suite de
  tests no cambia de comportamiento. El despliegue la activa
  (`ASSISTANT_CACHE_TTL=900`). El `ttl_s` del decorador es el máximo; el
  efectivo es `min(ttl_s, ASSISTANT_CACHE_TTL)` y `0` lo apaga del todo.
- No cachear respuestas del LLM (`chat.py` no la usa).

`X-Cache: hit|miss` en los routers: usar `ultimo_fue_hit()` justo después de
la llamada envuelta (best-effort, no thread-safe fino — suficiente para un
servicio de un solo worker).
"""

from __future__ import annotations

import functools
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

_LOCK = threading.Lock()
_ULTIMO_HIT = threading.local()


def _ttl_env() -> float:
    try:
        return max(0.0, float(os.environ.get("ASSISTANT_CACHE_TTL", "0")))
    except ValueError:
        return 0.0


def _clave(args: tuple, kwargs: dict) -> str:
    # los clientes inyectables (athena_client / neo4j_driver / driver) no
    # forman parte de la identidad del resultado -> se ignoran.
    kw = {k: v for k, v in kwargs.items() if k not in ("athena_client", "neo4j_driver", "driver")}
    return repr((args, sorted(kw.items())))


def ultimo_fue_hit() -> bool:
    """¿La última llamada cacheada en este hilo fue un acierto de caché?"""
    return bool(getattr(_ULTIMO_HIT, "valor", False))


def cacheado(ttl_s: float = 900.0, maxsize: int = 256) -> Callable:
    """Decorador de caché TTL+LRU. El TTL efectivo es
    `min(ttl_s, ASSISTANT_CACHE_TTL)`; con la env a `0` (por defecto) la
    función se llama siempre."""

    def deco(fn: Callable) -> Callable:
        store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            ttl = min(ttl_s, _ttl_env())
            if ttl <= 0:
                _ULTIMO_HIT.valor = False
                return fn(*args, **kwargs)
            k = _clave(args, kwargs)
            ahora = time.monotonic()
            with _LOCK:
                hit = store.get(k)
                if hit is not None and ahora - hit[0] < ttl:
                    store.move_to_end(k)
                    _ULTIMO_HIT.valor = True
                    return hit[1]
            _ULTIMO_HIT.valor = False
            valor = fn(*args, **kwargs)
            with _LOCK:
                store[k] = (ahora, valor)
                store.move_to_end(k)
                while len(store) > maxsize:
                    store.popitem(last=False)
            return valor

        wrapper.cache_clear = lambda: store.clear()  # type: ignore[attr-defined]
        wrapper.cache_len = lambda: len(store)  # type: ignore[attr-defined]
        return wrapper

    return deco
