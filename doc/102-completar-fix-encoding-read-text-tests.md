# 102 — Completar el fix de encoding en `.read_text()` que la tarea 097 dejó a medias

## Contexto

`doc/097-ci-minima.md` documentaba haber corregido 3 tests que llamaban a
`Path.read_text()` sin `encoding="utf-8"` explícito sobre fixtures JSON con
caracteres no ASCII (nombres reales de Madrid con tildes/eñes) — bug latente
en Windows (donde `read_text()` sin argumento usa la codificación del
sistema, `cp1252`, no UTF-8) que nunca falla en Linux/CI (donde el encoding
por defecto ya es UTF-8). Esta tarea de QA detectó que esa limpieza no fue
completa: quedaban 2 ficheros más con el mismo patrón.

## Qué se hizo

- Añadido `encoding="utf-8"` a las 7 llamadas a `.read_text()` señaladas en
  el enunciado:
  - `ingesta/tests/test_afluencia_lugares_madrid.py` (líneas 29, 30, 113, 134)
  - `ingesta/tests/test_barrios_distritos_madrid.py` (líneas 180, 194, 209)
- Repetida una búsqueda completa (`grep -rn "read_text()" --include="*.py" .`
  y también `grep -rn "\.read_text(" --include="*.py" . | grep -v
  "encoding="`) sobre todo el repositorio: confirmado que estas eran las
  únicas 7 llamadas sin `encoding=` explícito — no había ninguna más fuera
  de las señaladas en el enunciado.
- Cambio puramente mecánico: solo se tocó la llamada a `read_text()`, sin
  modificar ninguna lógica de test.

## Verificación

Esta EC2 no tenía `pytest`/`boto3`/`fastapi`/etc. instalados y el disco
raíz está muy limitado (898M libres al empezar) — instalar las
dependencias reales del proyecto con `pip install` normal habría escrito en
disco de forma no acotada. Se instalaron en su lugar en un directorio
`--target` bajo `/tmp` (tmpfs, respaldado por RAM, no disco persistente) y
se borró al terminar, sin dejar rastro en el disco del worktree ni en el
sistema:

```
python3 -m pip install --break-system-packages --target /tmp/pylibs102 \
  pytest requests boto3 fastapi "uvicorn[standard]" httpx "mcp>=2.0,<3" "neo4j>=5,<6"
PYTHONPATH=/tmp/pylibs102 python3 -m pytest ingesta/ procesamiento/ grafo/ asistente/ herramientas/ -q
# 841 passed, 1 skipped, 30 warnings, 12 subtests passed
rm -rf /tmp/pylibs102
```

Mismo resultado exacto (841 passed, 1 skipped) que la verificación
documentada en `doc/097-ci-minima.md` — la suite completa sigue en verde.

## Restricciones respetadas

- Cambio mecánico y acotado a las 7 llamadas señaladas — ninguna lógica de
  test modificada.
- Ninguna dependencia de Python instalada de forma persistente en el
  sistema ni en el worktree (todo en tmpfs, borrado al terminar) — la EC2
  tiene muy poco disco libre.

## Relevante para tareas futuras

- La limpieza de `encoding="utf-8"` en `.read_text()` iniciada en la tarea
  097 queda ahora completa en todo el repositorio (verificado con `grep`
  exhaustivo, no solo sobre los ficheros señalados en el enunciado).
- Esta EC2 no tiene un entorno Python con las dependencias del proyecto
  preinstaladas ni `python3-venv` disponible (`python3 -m venv` falla por
  falta de `ensurepip`). Para ejecutar la suite de tests localmente aquí,
  usar `pip install --break-system-packages --target /tmp/<dir>` (tmpfs) +
  `PYTHONPATH=/tmp/<dir> python3 -m pytest ...`, y borrar el directorio al
  terminar — no instalar con `pip install` a secas (falla por
  "externally-managed-environment") ni dejar paquetes instalados en disco
  persistente dado el poco espacio libre.
