---
id: 102
slug: completar-fix-encoding-read-text-tests
title: 'QA: quedan 2 ficheros de test con el mismo bug de encoding que la tarea 097
  dijo haber arreglado (3 de 5)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/102-completar-fix-encoding-read-text-tests
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-27T21:20:00+00:00'
updated_at: '2026-08-27T22:16:08.647291+00:00'
started_at: '2026-08-27T22:16:08.647266+00:00'
submitted_at: null
merged_at: null
---

## Hallazgo de QA (auditoría de la tarea 097, hallazgo menor)

`doc/097-ci-minima.md` dice que, montando la CI, se encontraron y
corrigieron "3 tests con `Path.read_text()` sin `encoding=\"utf-8\"`
explícito que fallaban en Windows (nunca en Linux/CI)". Correcto en lo que
arregló, pero **no fue una limpieza completa**: quedan 2 ficheros más con
el mismo patrón, leyendo fixtures JSON con nombres reales de Madrid
(barrios/distritos con tildes — `Peñagrande`, `Chamberí`, etc., el mismo
tipo de contenido no-ASCII que causaba el bug original en Windows):

- `ingesta/tests/test_afluencia_lugares_madrid.py` (líneas 29, 30, 113, 134)
- `ingesta/tests/test_barrios_distritos_madrid.py` (líneas 180, 194, 209)

Ninguno falla en Linux/CI (por eso pasó desapercibido igual que los 3
originales antes de la tarea 097), pero es el mismo bug latente para
cualquiera que ejecute estos tests en Windows.

## Objetivo

Terminar la limpieza que la tarea 097 empezó.

## Alcance concreto

- Añade `encoding="utf-8"` a las 7 llamadas a `.read_text()` señaladas
  arriba (mismo patrón que usó la tarea 097 para las otras 3).
- Repite una búsqueda completa (`grep -rn "read_text()" --include="*.py"`
  sin `encoding=`) sobre todo el repo para confirmar que no queda ninguna
  más, no solo estas 7.
- Corre la suite completa para confirmar que sigue en verde.

## Restricciones

- Cambio mecánico y acotado — no toques la lógica de los tests, solo la
  llamada a `read_text()`.

## Criterios de aceptación

- Ninguna llamada a `.read_text()` sin `encoding=` explícito en todo el
  repositorio.
- Suite completa en verde.
- Commit real.
