# VIC_25 — lint estático con ruff (ronda 4)

**Fecha:** 2026-08-30. `ruff` no estaba configurado en el repo (sin
`pyproject.toml`/`ruff.toml`, sin paso de lint en `.github/workflows/ci.yml`)
— primera vez que corre sobre esta base de código. Instalado solo en el
`.venv` local de esta EC2 para la auditoría (`pip install ruff`, no añadido a
ningún `requirements.txt`).

## Comando

```
ruff check ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/ tests/
```

**1237 hallazgos totales**, 1135 auto-corregibles. El volumen se explica
completamente por reglas de modernización de tipado y estilo que ningún
proyecto sin `ruff` desde el día uno pasa nunca limpio:

| Regla | Nº | Qué es |
|---|---|---|
| `UP037` | 695 | Anotación de tipo entre comillas innecesaria (`"Foo"` en vez de `Foo` con `from __future__ import annotations`) |
| `UP045` | 327 | `Optional[X]` en vez de `X \| None` (sintaxis pre-3.10) |
| `I001` | 41 | Imports sin ordenar |
| `DTZ001/007/011` | 38 | `datetime`/`date` sin zona horaria explícita |
| `RUF100` | 31 | `# noqa` que no suprime nada bajo la config *default* de ruff |
| `SIM117` | 19 | `with` anidados que podrían combinarse |
| `F401` | 13 | Import sin usar |
| `UP035` | 12 | Import de módulo *deprecated* (p. ej. `typing.List`) |
| `RUF012` | 11 | Valor por defecto mutable en atributo de clase |
| `B008` | 10 | Llamada a función en valor por defecto de un argumento |
| resto | ~40 | Casos sueltos de más de 15 reglas distintas, 1-7 apariciones cada una |

Todo lo de arriba (excepto lo triado abajo) es estilo/modernización puro,
cero cambio de comportamiento, y coherente con "nadie corrió un linter
nunca en este repo". No se aplicó ningún `--fix`.

## Triaje de lo que sí tenía potencial de bug real

Revisado a mano, con lectura de código real (no solo el conteo), cada
categoría con potencial de esconder un bug:

- **`DTZ001/007/011` (38, timezone)** — el hallazgo con más volumen y el
  único que en un sistema de series temporales en tiempo real podría ser un
  bug real (desfase horario Madrid/UTC). Revisado caso por caso:
  - La mayoría (~28) son en `tests/*.py`: `datetime(...)` naive en
    fixtures, sin efecto en producción.
  - `ingesta/capturas/aforos_peatones_bicicletas_madrid.py:423` y
    `trafico_madrid.py:113`: parsean naive y luego hacen
    `.replace(tzinfo=MADRID_TZ)` en la misma función — ruff no ve el
    `.replace` posterior y marca falso positivo; el resultado final sí es
    aware.
  - `agenda_eventos_madrid.py` (`_parse_municipal_datetime`,
    `_parse_esmadrid_date`, 3 casos): sí devuelven naive de verdad, pero es
    una decisión documentada explícitamente en el docstring de
    `procesamiento/silver_gold/agenda_eventos/transform.py` (sección
    "`start_datetime`: formato distinto según la fuente, ninguno con zona
    horaria") — `validate_record` exige que sea parseable, no que tenga
    hora ni zona, a propósito. No es un descuido, es una decisión de diseño
    ya razonada por escrito.
  - `calendario_laboral_madrid.py:226`: solo extrae `.date()`, sin
    componente de hora — la zona horaria es irrelevante aquí.
  - `modelado/training/retrain_nightly.py:68,87`: usa
    `datetime.date.today()` (hora del servidor) en vez de una fecha
    explícita en UTC/Madrid. El cron corre a las 3:30 UTC — con el offset
    de Madrid (+1/+2h) eso cae siempre bien después de la medianoche en
    ambas zonas, así que hoy no es un bug con este horario de cron. Es
    frágil (dependería del huso horario del sistema y del horario exacto
    del cron) pero no es un bug reproducible ahora mismo — no amerita un
    `FIL_*`, solo queda anotado aquí por si el cron cambia de hora alguna
    vez.
  - **Veredicto: sin bug real.**

- **`RUF012` (11, atributo de clase mutable)** — las 11 apariciones son en
  `ingesta/tests/test_*.py`, atributos de clases mock/fixture de test. Sin
  efecto en producción. **Sin bug real.**

- **`B008` (10, llamada en valor por defecto)** — las 10 son
  `Query(...)` de FastAPI en `asistente/routers/*.py`. Es el patrón
  *recomendado* por la propia documentación de FastAPI (`Query` está
  diseñado para usarse así, con inyección de dependencias); `ruff` no
  distingue este caso especial del antipatrón genérico de Python. **Falso
  positivo de la regla, sin bug real.**

- **`F401`/`F841`/`RUF059` (13+2+4, imports/variables sin usar)** —
  revisados uno a uno: imports muertos (`math` en `prevision_grafo.py`,
  `statistics`/`Optional` en `lambda_costes.py`, etc.) y variables
  desempaquetadas sin usar en tests (`ew`, `X`, `fecha`, `comp`). Código
  muerto real, pero sin ningún efecto funcional — no cambian ningún
  resultado ni esconden una llamada rota. Limpieza cosmética, no bug.

- **`S110`/`BLE001` (2+1, `except`/`pass` amplio)** — las dos de
  `S110` (`grafo/cypher.py:283`, `mlflow_setup.py:90`) ya llevan un
  `# noqa: BLE001` con la razón explícita en el propio código ("el driver
  ya está roto, da igual" / reintento de promoción de champion). Decisión
  ya razonada y documentada, no un descuido. La de `BLE001` en
  `modelado/tests/test_ml07.py:67` es un `try/except` de test comprobando
  si `onnx` es importable. **Sin bug real.**

- **`PLR0124` (1, comparación consigo mismo)** —
  `modelado/training/retrain_nightly.py:49`:
  `if skill_nuevo != skill_nuevo:  # NaN`. Es el idioma clásico de Python
  para detectar `NaN` (`x != x` es `True` solo si `x` es `NaN`) — el propio
  comentario `# NaN` ya lo documenta. `ruff` no reconoce el idioma.
  **Falso positivo, sin bug real.**

- **`PYI034` (3, `__enter__` debería devolver `Self`)** — en
  `grafo/cypher.py:287` (`Neo4jLoader.__enter__`) el método ya devuelve
  `self` correctamente; solo usa la anotación de tipo antigua
  (`"Neo4jLoader"` en vez de `typing.Self`, PEP 673). Comportamiento
  correcto, solo estilo de tipado desactualizado. **Sin bug real.**

- **`RUF100` (31, `noqa` sin efecto)** — todos son `# noqa: BLE001` /
  `# noqa: F401` / `# noqa: E712` escritos por los desarrolladores
  anticipando un linter que nunca llegó a configurarse: bajo la config
  *default* de `ruff` (sin `pyproject.toml`), reglas como `BLE001`/`E712`
  no están activadas por defecto, así que el `noqa` no suprime nada *para
  ruff* — pero la razón sigue siendo válida como documentación humana.
  Confirma el hallazgo central de esta ronda (no hay lint configurado),
  no es un hallazgo nuevo en sí mismo.

## Conclusión

**Cero `FIL_*` nuevos de `VIC_25`.** El barrido estático con `ruff`
corrobora, desde un ángulo completamente distinto (análisis estático en
vez de ejecución en vivo), lo que las rondas 1-3 ya habían verificado en
vivo: no hay bugs funcionales escondidos en el código actual. Todo el
volumen de hallazgos es higiene de estilo/tipado nunca aplicada (normal en
un repo sin linter desde el origen) o falsos positivos de reglas que no
entienden patrones específicos del dominio (FastAPI `Query`, el idioma
`x != x` para `NaN`, `.replace(tzinfo=...)` tras un parseo naive).

**Recomendación (no un `FIL_*`, una observación para el track de
mantenimiento):** si el equipo quiere adoptar `ruff` de forma permanente,
lo más barato es un `pyproject.toml` con un `select` reducido (`E`, `F`,
`I`) y `ruff check --fix` una vez para limpiar los 1135 auto-corregibles,
dejando fuera `UP037`/`UP045`/`DTZ*`/`B008` (generan ruido específico de
este proyecto, como se ha triado arriba). No se propone como ticket porque
es una decisión de proceso del equipo, no un defecto a corregir.
