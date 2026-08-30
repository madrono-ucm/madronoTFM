---
kind: vikt
title: "Recorrido end-to-end reproducible para la defensa (muestra -> pipeline -> Gold -> grafo -> asistente + ML)"
owner: Pista Memoria — QA + documentación (interactivo)
status: done
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

## Hecho (30/8)

`doc/VIKT-06-recorrido-e2e.md` — guion completo, comandos + salida real
capturada verificando en vivo (no inventada):

- **Ingesta→Bronze**: fixture real committeado (`pm_sample.xml`, captura
  real de `informo.madrid.es` del 12/8) → `parse_records` real.
- **Bronze→Silver→Gold**: `bronze_to_silver`/`aggregate_silver_to_gold`
  reales sobre esa misma muestra (Python puro, sin Spark, mismo criterio
  que el resto del repo) + una consulta Athena real contra
  `gold.trafico_por_punto_hora` (punto 4398, 30/8).
- **Grafo**: consulta Cypher real documentada con su código fuente exacto
  (`asistente/neo4j_client.py`) y el conteo real de `VIC_10` — **no
  re-ejecutada en vivo**, credenciales Neo4j bloqueadas por el clasificador
  de modo automático de esta sesión (sin buscar rodeos). Anotado
  explícitamente como limitación, según pide el propio ticket.
- **Asistente**: servidor MCP real levantado en `stdio` con un
  `ClientSession` real (no en-proceso) — `initialize`+`list_tools` (9 tools
  reales) + `call_tool` de `calidad_aire` (éxito, solo Athena) y
  `calidad_aire_prevista` (éxito, previsión ONNX real 72,0→52,0 µg/m³ a 3h)
  + `trafico_prevista` bajo fallo genuino de Neo4j (degradación elegante
  real, no simulada).
- **ML**: registry MLflow real (6 `@champion` reales, consistentes con los
  `.onnx` de la sección de asistente) + evidencia real del reentrenamiento
  nocturno (`historial.csv`: un rechazo real y una promoción real el mismo
  día) + comando de backtest documentado.

**Hallazgo nuevo durante la verificación** (no en el alcance original de
este ticket, archivado aparte): `opciones_movilidad`/`eventos_cercanos` son
las únicas 2 de 9 tools sin `output_schema` MCP anunciado (limitación real
del SDK `mcp` con retornos `list[BaseModel]`, no rompe la llamada) → ver
[`FIL_24`](FIL_24_mcp-output-schema-list-tools.md).
