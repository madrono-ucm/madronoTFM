---
kind: vic-eval
title: "Evaluación técnica — ingesta/"
owner: Claude (QA)
status: done
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test — ningún cambio de código aquí; cualquier hallazgo que
implique cambiar código se empaqueta como ticket `FIL_*` aparte.

## Alcance

- `python3 -m unittest discover -s ingesta/tests -t .` — suite completa.
- Verificar que los 24 módulos de captura listados en `ingesta/README.md`
  existen y tienen su `lambda_handler` real (no solo código de muestra).
- Spot-check en vivo de 2-3 fuentes reales (no solo confiar en la última
  ejecución de Lambda — invocar `capture_all()`/lo que corresponda contra
  la fuente real, o verificar el Bronze más reciente en S3).

## Criterios de aceptación

- Resultado real de la suite (nº de tests, verde/rojo).
- Al menos 2-3 fuentes verificadas en vivo, con resultado real.
- Cualquier discrepancia código↔realidad documentada, con ticket `FIL_*`
  si implica un cambio de código.

## Hecho (29/8)

- `python3 -m unittest discover -s ingesta/tests -t .` → **303 passed**
  (tras instalar `netCDF4`/`beautifulsoup4`, faltaban en el `.venv` pero
  ya estaban en `ingesta/requirements.txt` — no es un hallazgo real, solo
  un entorno incompleto).
- Spot-check en vivo real contra 3 fuentes: `trafico_madrid` (4893 puntos
  reales descargados de `informo.madrid.es` ahora mismo), `calidad_aire_madrid`
  (123 registros reales), `emt_incidencias_madrid` (111 incidencias reales,
  feed RSS en vivo). Los 24 módulos de `ingesta/capturas/` existen y tienen
  `lambda_handler` real (confirmado en sesiones anteriores, `FIL_02`/`FIL_03`-`05`).
- Hallazgo menor (no bloqueante): `trafico_madrid.py` tiene un docstring
  desactualizado que dice "todavía no hay infraestructura S3 aplicada (ver
  tarea 001)" — la infra sí está aplicada desde hace muchas tareas; el
  código real usa `BronzeWriter` (tarea 025), este comentario es un
  residuo del módulo original. Cosmético, se agrupa en un ticket `FIL_*`
  de limpieza menor junto con otros hallazgos de esta ronda de evaluación,
  no amerita uno propio.
