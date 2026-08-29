---
kind: vic-eval
title: "Evaluación técnica — asistente/ (las 7 tools, en vivo)"
owner: Claude (QA)
status: done
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s asistente/tests -t .` — suite completa.
- Verificación en vivo de las 7 tools contra Athena/Neo4j/ONNX reales
  (`calidad_aire`, `trafico_cercano`, `afluencia_estimada`,
  `disponibilidad_aparcamiento`, `eventos_cercanos`, `opciones_movilidad`,
  `calidad_aire_prevista`) — esta última ya se verificó en una sesión
  anterior de esta misma conversación, las otras 6 no se han vuelto a
  probar en vivo desde sus tareas originales.

## Criterios de aceptación

- Resultado real de la suite.
- Cada una de las 7 tools invocada al menos una vez contra datos reales,
  con el resultado real anotado.
- Cualquier tool rota o degradada, documentada, con ticket `FIL_*` si
  implica un cambio de código.

## Hecho (29/8)

- `python3 -m unittest discover -s asistente/tests -t .` → **74 passed**
  (tras instalar el paquete `mcp`, faltaba en el `.venv`).
- Las 7 tools verificadas en vivo contra Athena/Neo4j reales:
  `calidad_aire`, `trafico_cercano`, `afluencia_estimada`,
  `disponibilidad_aparcamiento`, `eventos_cercanos`, `opciones_movilidad`
  (con `momento=2026-08-28T12:00`, dentro de una ventana con datos
  completos) y `calidad_aire_prevista` (ya verificada antes en esta misma
  sesión). Las 7 devuelven resultados reales y coherentes (tráfico
  "fluido", calidad del aire "buena" PM10 11 µg/m³, aparcamiento con
  plazas libres reales, eventos reales del Retiro, etc.).
- **Hallazgo real, no de `asistente/` sino de datos**: probando primero
  con `momento=2026-08-29T15:00` (ayer), varias tools devolvían
  `sin_datos` pese a que Neo4j sí encontraba estaciones cercanas reales.
  Investigado hasta la causa: **6 datasets (`trafico`, `bicimad`,
  `transporte_publico_emt`, `meteorologia`, `calidad_aire`,
  `aparcamientos`) tienen entre 17 y 21 horas perdidas el 29/8** — el
  incidente de la tarea 106/`FIL_09` (librería de Glue rota) causó 19
  fallos horarios consecutivos en `trafico_bronze_to_silver` (01:10-19:10
  UTC), y esas horas **nunca se rellenaron** tras el fix — `FIL_09` solo
  verificó frescura por fecha, no completitud por hora. Ver
  [`FIL_12`](FIL_12_gap-horario-incidente-fil09-sin-backfill.md). Repetida
  la prueba con un `momento` de un día completo (28/8) para separar este
  problema de datos de la lógica de las tools, que es correcta.
