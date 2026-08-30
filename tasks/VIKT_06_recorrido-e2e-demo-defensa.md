---
kind: vikt
title: "Recorrido end-to-end reproducible para la defensa (muestra -> pipeline -> Gold -> grafo -> asistente + ML)"
owner: Pista Memoria — QA + documentación (interactivo)
status: pending
created_at: "2026-08-30"
depends_on: [FIL_13, FIL_15]
---

## Contexto

No existe un guion único que demuestre el sistema entero funcionando. Es lo
que más de-arriesga la defensa: poder enseñar, paso a paso y de forma
reproducible, que un dato entra por un lado y sale como una respuesta del
asistente apoyada en una previsión de ML.

## Objetivo

`doc/VIKT-06-recorrido-e2e.md` — un guion con comandos copiables y salidas
esperadas, que recorra:

1. **Ingesta** — una muestra real de un productor (`python -m
   ingesta.capturas.<x>` o la fixture commiteada) → cómo se ve en Bronze.
2. **Procesamiento** — `transform` + `aggregate` (Python, sin Spark) sobre
   esa muestra → filas Gold; y/o una consulta Athena a la Gold ya presente.
3. **Grafo** — una consulta Cypher real que resuelve un lugar → sus
   estaciones `PROXIMO_A`.
4. **Asistente** — levantar el MCP en `stdio`, `list_tools`, y llamar:
   `calidad_aire(zona)`, `calidad_aire_prevista(zona, h3)` y
   `trafico_prevista(...)` para un lugar y momento reales; enseñar el
   envoltorio de respuesta (valor + versión de modelo + ventana de datos).
5. **ML** — `mlflow ui` mostrando los `@champion`; `modelado/evaluation/
   backtest.py` mostrando la curva de skill.

Incluir qué se ve si el pipeline se **reanuda** vs congelado.

## Criterios de aceptación

- Otra persona reproduce el recorrido completo desde el documento, sin
  conocimiento previo del repo.
- Cubre las 3 capas (datos, ML, asistente) y al menos 2 tools `*_prevista`.
- Material listo para un screencast de la defensa (orden, tiempos, qué
  resaltar).

## Restricciones

- No toca el `.docx`. Produce sólo `doc/`.
- Datos reales, no inventados; si algo no se puede mostrar (Spark real),
  decirlo.
