---
id: 79
slug: asistente-tool-calidad-aire
title: 'Asistente: primera tool real (calidad_aire) contra Athena, de extremo a extremo'
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-23T18:00:00+00:00'
updated_at: '2026-08-24T20:20:00+00:00'
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

El esqueleto del asistente (tarea 044, `asistente/`) tiene 5 `tools` MCP
definidas con `NotImplementedError` — ninguna lee datos reales. Con
Silver/Gold en producción y Athena fiable (tareas 041-068), ya no hay ningún
bloqueo técnico para implementar la primera de verdad. Esta tarea escoge
deliberadamente **una sola tool, de extremo a extremo**, en vez de varias a
la vez — alcance pequeño a propósito: varias tareas de esta sesión han
agotado presupuesto por cubrir demasiado dataset/pieza a la vez (ver p.ej.
`doc/055`/`doc/057`).

**Tool elegida: `calidad_aire(zona, momento=None)`** — la más simple de las
5 (una sola fuente, `gold.calidad_aire_por_estacion_contaminante_hora`, ya
verificada en las tareas 049/066/068), y la que menos depende de piezas
todavía no listas (a diferencia de `opciones_movilidad`, que cruza 3
datasets, o `afluencia_prevista`, bloqueada sin `GOOGLE_MAPS_API_KEY`).

**Simplificación deliberada de `zona`**: la tabla Gold no tiene una
dimensión de barrio/distrito (esa resolución espacial es el trabajo del
grafo, tarea 043/067-071, tareas 079+ siguientes una vez cargado). Para esta
tarea, `zona` se resuelve contra `station_name`/`station_id` de la propia
tabla (coincidencia por texto sobre el nombre de la estación — p.ej. "Ramón
y Cajal", "Plaza del Carmen"), no contra un nombre de barrio real. Documenta
esta limitación en la respuesta del asistente cuando aplique (p.ej. si no
encuentra ninguna estación que coincida). No implementes resolución por
distrito/barrio aquí — es la tarea que depende del grafo.

Columnas reales de `gold.calidad_aire_por_estacion_contaminante_hora`
(base de datos `madrono-tfm_dev_gold`, partición `date`): `station_id`,
`station_name`, `pollutant`, `pollutant_name`, `unit`, `hour`,
`avg_value`, `max_value`, `min_value`, `samples_count`, `lat`, `lon`.

## Objetivo

Implementar `calidad_aire` con una consulta Athena real, montar el
servidor MCP dentro de la app FastAPI (paso ya identificado como pendiente
en `asistente/README.md`), y devolver una `RespuestaAsistente` real y
trazable a los datos.

## Alcance concreto

1. `asistente/mcp_agent/tools.py`: implementa `calidad_aire(zona,
   momento=None)`. Reutiliza el patrón de consulta a Athena ya establecido
   en `grafo/extract.py` (tarea 069: `boto3` +
   `start_query_execution`/`get_query_execution`/`get_query_results` sobre
   el workgroup `madrono-tfm-dev-silver-gold`, con el mismo backoff de
   sondeo) — no reinventes el mecanismo.
   - Filtra por `station_name`/`station_id` conteniendo `zona` (case
     insensitive), y por la partición `date` correspondiente a `momento`
     (o al día de hoy en hora de Madrid si `momento` es `None` — usa
     `asistente/timeutils.py::now_madrid()`).
   - Si no hay ninguna estación que coincida: la tool debe devolver un
     resultado explícito de "sin datos", no lanzar una excepción sin
     capturar.
   - Si hay varias estaciones que coinciden: agrégalas de forma razonable
     (p.ej. la de mayor `avg_value` por contaminante, o lista las
     principales) — decide un criterio simple y documéntalo, no hace falta
     sofisticación aquí.
2. `asistente/mcp_agent/server.py`/`asistente/main.py`: monta
   `MCPServer.streamable_http_app()` en la app FastAPI (`FastAPI.mount()`),
   combinando el `lifespan` de ambas apps — el propio `asistente/README.md`
   ya explica por qué hacía falta y por qué se dejó pendiente.
3. Construye la `RespuestaAsistente` (veredicto/fiabilidad/explicación/
   fuentes, ver `asistente/models/respuesta.py`) a partir del resultado real
   de la tool — `fiabilidad` debe reflejar si se encontró la estación o no,
   `fuentes` debe citar el dataset y la estación consultada.
4. Añade un router nuevo (`asistente/routers/`, sigue el patrón de
   `health.py`) que exponga esta consulta vía HTTP para poder probarla sin
   un cliente MCP.
5. Tests: amplía `asistente/tests/test_mcp_tools.py` con la lógica de
   `calidad_aire` mockeando Athena (sin conexión real en los tests, mismo
   criterio que `grafo/tests/test_extract.py`), y añade un test del router
   nuevo.
6. Verifica con al menos una invocación real (arranca el servicio local,
   `curl`/`httpx` contra el router nuevo con una zona real de Madrid, p.ej.
   "Ramón y Cajal" o "Retiro") que la respuesta trae datos reales de Athena,
   no simulados.

## Restricciones

- Alcance: **solo la tool `calidad_aire`** — no implementes las otras 4
  aunque parezca poco esfuerzo adicional. `disponibilidad_aparcamiento` y
  las demás son tareas de seguimiento separadas.
- No implementes resolución de barrio/distrito real — usa la simplificación
  de `zona` descrita arriba.
- No despliegues nada (sin infraestructura Terraform nueva, mismo criterio
  que la tarea 044) — esta tarea es sobre el código del servicio, no sobre
  su despliegue.
- No instales ni tampoco elimines dependencias de `asistente/requirements.txt`
  salvo que de verdad haga falta una nueva (documenta por qué si la añades).

## Criterios de aceptación

- `calidad_aire` devuelve datos reales de Athena, verificado con al menos
  una invocación real contra una estación real de Madrid.
- El servidor MCP está montado dentro de la app FastAPI, con el `lifespan`
  combinado correctamente.
- Tests en verde, incluida la lógica de la tool mockeando Athena.
- `asistente/README.md` actualizado: ya no dice "esqueleto, no funcional"
  sin matices — refleja que `calidad_aire` es real y el resto siguen
  pendientes.
