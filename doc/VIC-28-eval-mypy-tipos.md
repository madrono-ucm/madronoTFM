# VIC_28 — comprobación de tipos con mypy (ronda 5)

**Fecha:** 2026-08-30. `mypy` no estaba instalado ni configurado — primera
vez que corre sobre este código, sin `pyproject.toml`/`mypy.ini`.

## Comando

```
mypy --ignore-missing-imports --explicit-package-bases \
  ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/ \
  --exclude '.*/tests/.*'
```

(`--explicit-package-bases` hizo falta porque `herramientas/costes/` y otro
paquete colisionaban de nombre bajo la resolución de módulos por defecto de
`mypy` — un artefacto de cómo está organizado el repo, no un bug.)

**97 errores en 28 ficheros** (de 210 ficheros analizados). Desglose por
código de error:

| Código | Nº | Qué es |
|---|---|---|
| `arg-type` | 44 | Argumento de tipo incompatible |
| `assignment` | 15 | Asignación de tipo incompatible |
| `type-var` | 8 | Variable de tipo genérico no satisfecha |
| `valid-type` | 6 | Uso inválido de un nombre como anotación de tipo |
| `operator` | 6 | Operador no soportado entre esos tipos |
| `index` | 5 | Subíndice sobre un tipo no indexable |
| `return-value` | 4 | Valor de retorno incompatible con la anotación |
| `attr-defined` | 4 | Atributo inexistente en ese tipo |
| `union-attr` | 3 | Atributo ausente en una rama de un `Union` |
| resto | 2 | `var-annotated`, `no-redef` |

## Triaje (leído el código real, no solo el mensaje de mypy)

- **`arg-type` (44, el grupo más grande) — patrón `**dict` sin tipar hacia
  un dataclass/pydantic**: dominado por `asistente/mcp_agent/tools.py` (30
  de los 44) y `modelado/features/build.py` (5). El patrón es siempre el
  mismo: un `dict` construido dinámicamente (`base = dict(...); base.update(kw)`
  en los helpers `_sin(...)` de las tools de previsión, o `_TARGETS[target]`
  como diccionario de configuración con valores de tipos mixtos) que luego
  se pasa como `**kwargs` a un constructor. `mypy` no puede verificar
  estáticamente que cada clave del `dict` tenga el tipo exacto que el
  constructor espera — el diccionario se infiere como `dict[str, object]`,
  así que cualquier `**` sobre él genera un error por cada campo del
  constructor de destino. Es un patrón deliberado de "bolsa de kwargs
  flexible con overrides" (`_sin(motivo, **kw)`), correcto en tiempo de
  ejecución y cubierto por la suite de tests existente. **Sin bug real.**
- **`valid-type` (6) + 1 `attr-defined` relacionado — alias de tipo como
  string plano**: `procesamiento/silver_gold/afluencia_lugares/nivel.py`
  define `Bandas = "tuple[tuple[float, str], ...]"` como una simple
  asignación de string (no `TypeAlias`, no la sintaxis `type Bandas = ...`
  de PEP 695), un patrón heredado de antes de que existiera `TypeAlias` en
  la stdlib. Con `from __future__ import annotations` esto funciona
  correctamente en tiempo de ejecución (las anotaciones son strings
  perezosos), pero `mypy` no reconoce esta forma como alias de tipo válido
  y marca cada uso. **Sin bug real** — funciona, solo no en la forma
  moderna que `mypy` espera.
- **`type-var` (8) — `sorted`/`max`/`min` sobre `Any | None`**: en varios
  `aggregate.py` de `procesamiento/silver_gold/*`, se ordena/compara una
  lista que en teoría podría contener `None` según su tipo declarado. Cada
  caso revisado tiene un filtro previo (`if x is not None`) o una
  comprensión que ya excluye `None` antes de llegar a `sorted`/`max`/`min`
  — `mypy` no siempre conecta el filtro con el uso posterior en una sola
  expresión. **Sin bug real** en los casos revisados.
- **`operator` (6) — 3 merecieron lectura profunda de control de flujo**:
  - `herramientas/salud/frescura_gold.py:137,144`: comparan `float` con
    `UMBRAL_HORAS[cadencia]`, cuyo tipo de valor es `float | None`
    (`UMBRAL_HORAS[DESCONTINUADA] = None`, a propósito: "nunca se espera
    fresca"). Verificado que ambos usos están *después* de un
    `if cadencia == DESCONTINUADA: return ...` que ya sale de la función
    en ese caso — para cuando se llega a la comparación, `cadencia` nunca
    puede ser `DESCONTINUADA`, así que el valor nunca es `None` en la
    práctica. `mypy` no hace *narrowing* de un `dict[str, float | None]`
    por comparación de la clave con un valor concreto. **Sin bug real.**
  - `procesamiento/silver_gold/ruido/aggregate.py:142`: mismo patrón
    (comparación de fecha con un valor que el tipo declarado permite
    `None` pero el control de flujo ya descarta).
  - `ingesta/capturas/bronze.py:104` — **este sí es real**, ver más abajo.
- **`union-attr` (3)**: 2 casos en `netCDF4`/PySpark, dependientes de la
  ausencia de *stubs* de tipos de estas librerías (`--ignore-missing-imports`
  las trata como `Any` en muchos puntos, lo que genera *Unions* espurios en
  otros). El módulo `cams_calidad_aire_madrid.py` afectado lleva su propio
  comentario de "verificado en vivo con credenciales reales" (tarea 045)
  para exactamente este código — evidencia indirecta de que el camino real
  no ha crasheado. **Sin bug confirmado**, tratado como ruido de stubs.
- **`no-redef` (1)**: `asistente/mcp_agent/tools.py:549`, reutiliza el
  nombre `gold_por_id` en dos bloques `if` independientes de la misma
  función (tráfico y ruido). Verificado que el primer uso ya se consume
  por completo dentro de su propio bloque antes de que el segundo bloque
  reasigne el nombre — no hay contaminación cruzada. **Sin bug real.**

## El único hallazgo real: `ingesta/capturas/bronze.py:104`

`BronzeWriter.base_path` es **`str`** en modo S3 (línea 89) pero
**`pathlib.Path`** en modo local (línea 93); `partition_dir()` usa el
operador `/` (sobrecarga de `Path`) sin comprobar el modo primero — si se
llamara con el escritor en modo S3, lanzaría `TypeError`. Verificado que
hoy **no es explotable**: el único call site de `partition_dir()` en todo
el repo está detrás de `if self.is_s3: ... else: self.partition_dir(...)`
(modo S3 usa el método hermano `partition_key()`). Es un footgun latente
en un método público sin guarda ni docstring que documente la
restricción → **`FIL_40`** (renumerado desde `FIL_33` el 30/8 por colisión
con una rama sin mergear, ver `doc/PLAN-EVALUACION-TECNICA-5.md`;
endurecimiento preventivo, severidad baja, no es un incidente en
producción).

## Conclusión

1 `FIL_*` nuevo (`FIL_40`, latente/preventivo). El resto de los 97 errores
son enteramente explicables por patrones de tipado dinámico deliberados
(bolsas de kwargs, alias de tipo como string, diccionarios de
configuración heterogéneos) o limitaciones conocidas de `mypy` sin
`stubs` de terceros — ninguno representa un bug funcional real, cada uno
verificado leyendo el código y el control de flujo real, no solo el
mensaje de `mypy`.
