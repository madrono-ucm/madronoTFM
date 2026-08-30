---
kind: fil
title: "BronzeWriter.partition_dir() usa `self.base_path / ...` pero base_path es str en modo S3 -- crash latente si se llama fuera de write_batch"
status: pending
created_at: "2026-08-30"
source: "VIC_28 (ronda 5 de evaluación técnica, mypy)"
severity: baja (latente, no reproducida en producción)
---

## Qué está roto (verificado en vivo)

`mypy` (instalado por primera vez en esta sesión) sobre `ingesta/capturas/bronze.py`
marca `bronze.py:104: error: Unsupported left operand type for / ("str")  [operator]`.
Leído el código real:

```python
# __init__ (línea 84):
def __init__(self, base_path: "str | os.PathLike[str]", dataset: str):
    base_path_str = str(base_path)
    if base_path_str.startswith(S3_URI_PREFIX):
        self.base_path = base_path_str.rstrip("/")          # <- str
        self.s3_bucket, self.s3_prefix = _parse_s3_uri(self.base_path)
        ...
    else:
        self.base_path = Path(base_path)                    # <- pathlib.Path
        ...

@property
def is_s3(self) -> bool:
    return self.s3_client is not None

def partition_dir(self, moment: datetime) -> Path:           # línea 102
    return (
        self.base_path                                       # línea 104
        / self.dataset
        / f"fecha={moment:%Y-%m-%d}"
        / f"hora={moment:%H}"
    )
```

`self.base_path` es **`str` en modo S3** y **`pathlib.Path` en modo
local**, pero `partition_dir()` usa el operador `/` (sobrecarga de
`Path.__truediv__`) incondicionalmente, sin comprobar `self.is_s3`
primero. Si `partition_dir()` se llama alguna vez con un
`BronzeWriter` configurado en modo S3, lanza
`TypeError: unsupported operand type(s) for /: 'str' and 'str'`.

## Por qué importa

Verificado que **hoy no es un bug reproducible en producción**: el único
call site de `partition_dir()` en todo el repo
(`grep -rn "\.partition_dir(" ingesta/`) es dentro de
`write_batch()` (línea 148), y ese call site está detrás de un
`if self.is_s3: ... else: out_dir = self.partition_dir(moment)` — solo se
llama en modo local, nunca en modo S3 (el modo S3 usa `partition_key()`,
el método hermano documentado como "equivalente a `partition_dir` para el
modo S3").

Pero `partition_dir()` es un método público (sin prefijo `_`, sin
docstring que diga "solo modo local"), así que es un footgun latente:
cualquier código nuevo (un test que instancie `BronzeWriter` en modo S3 y
llame `partition_dir()` directamente para depurar, o un futuro refactor
que junte las dos ramas de `write_batch`) puede reintroducir esta llamada
en el peor sitio y romper en producción con un `TypeError` en vez de un
error claro. El coste de blindarlo ahora es mínimo.

## Qué hacer (propuesto, no aplicado aquí)

Opción mínima (sin cambiar la API pública): añadir una guarda explícita al
principio del método, para que el fallo sea inmediato y explicativo en vez
de un `TypeError` de operador confuso si alguna vez se llama mal:

```python
def partition_dir(self, moment: datetime) -> Path:
    """Solo modo local -- en modo S3 usar `partition_key()`."""
    if self.is_s3:
        raise RuntimeError("partition_dir() no aplica en modo S3; usar partition_key()")
    return (
        self.base_path
        / self.dataset
        / f"fecha={moment:%Y-%m-%d}"
        / f"hora={moment:%H}"
    )
```

Alternativa más profunda (no recomendada solo para esto): tipar
`self.base_path` como `Path | str` explícitamente y añadir un
`# type: ignore[operator]` documentado -- más ruido que la guarda de
arriba para el mismo resultado.

## Restricciones

- No se ha aplicado el cambio aquí (ticket de solo lectura, `mypy`
  instalado solo en el `.venv` local para esta auditoría).
- No es un incidente en producción: no hay ninguna llamada real a
  `partition_dir()` en modo S3 hoy. Prioridad baja, tratar como
  endurecimiento preventivo, no como hotfix urgente.

## Criterios de aceptación

- Guarda añadida (o equivalente) que falla con un mensaje claro si
  `partition_dir()` se llama con `self.is_s3 == True`.
- Suite de `ingesta/tests/` (en particular la de `bronze.py`, si existe)
  sigue en verde.
- `mypy ingesta/capturas/bronze.py` ya no reporta el error `[operator]`
  en esta línea (tras la guarda, `self.base_path` en esa rama del código
  es inequívocamente `Path` para cualquier lector humano, aunque mypy no
  vaya a estrecharlo automáticamente sin una comprobación explícita de
  `isinstance`).
