---
kind: vic-eval
title: "Evaluación técnica — modelado/ (ML_01-ML_10)"
owner: Claude (QA)
status: done
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s modelado/tests -t .` — suite completa
  (instalar `torch` si hace falta para `ML_05`, disco ya no es un
  problema tras el resize de la tarea 104).
- Confirmar que los artefactos reales (`modelado/evaluation/artifacts/`)
  siguen siendo consistentes entre sí (Tabla 3 de la memoria vs
  `comparacion_todos.csv`, etc.).
- Estado de los gaps ya conocidos: `ML_01` sin join real de meteo/AEMET ni
  festivos reales, STGNN sin exportar a ONNX.

## Criterios de aceptación

- Resultado real de la suite.
- Confirmación de que los artefactos citados en la memoria siguen
  existiendo y coincidiendo.
- Cualquier discrepancia documentada, con ticket `FIL_*` si implica un
  cambio de código.

## Hecho (29/8)

- `python3 -m unittest discover -s modelado/tests -t .` → **61 passed**
  (tras instalar `torch`, faltaba en el `.venv`; ya no hay problema de
  disco tras el resize de la tarea 104 — 9,4G libres tras instalarlo).
- Artefactos reales de `modelado/evaluation/artifacts/estudios/` siguen
  presentes y consistentes con la Tabla 3 de la memoria (verificado
  `comparacion_trafico.csv` contra los números ya citados en `VIKT_03`).
- **Descubierto (no documentado en ningún ticket)**: el gap de `ML_01`
  que la memoria describe como futura línea (§7.5 — "join real de
  meteo/previsión AEMET y festivos reales del calendario laboral, hoy sin
  implementar") **ya está cerrado por otra sesión**:
  `modelado/features/exogenas.py` (nuevo) implementa el join real de meteo
  observada (estación más cercana) y previsión AEMET ("la previsión de
  ayer para hoy", sin fuga), y `modelado/features/build.py` ya carga
  festivos reales del calendario laboral (`_cargar_festivos`), todo con
  tests (`test_exogenas.py`, `test_build.py`, incluidos en los 61 que
  pasan). No hay ningún ticket `ML_*`/`FIL_*` que documente este trabajo
  todavía. **Anotado para `VIC_15`**: la memoria (que yo mismo escribí en
  `VIKT_03`) sigue describiendo esto como pendiente — hay que corregirlo
  si `VIC_15` confirma que ya está realmente en producción (no solo en
  código/tests, sino usado en un panel real).
- STGNN sigue sin exportar a ONNX (bloqueado por `torch.export`, sin
  cambios, ya documentado) — no es un hallazgo nuevo.
