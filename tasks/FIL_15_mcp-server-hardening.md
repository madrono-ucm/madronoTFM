---
kind: fil
title: "Endurecer el servidor MCP: transporte, envoltorio de respuesta, degradación elegante"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: [FIL_13]
---

## Resolución (2026-08-30)

- **Envoltorio.** `RespuestaPrevision` en `asistente/models/respuesta.py`;
  `CalidadAirePrevista` y `TraficoPrevista` **heredan** de él (no rename a
  esquema envoltorio/detalle — ya compartían de facto los campos, sólo
  faltaba factorizarlos; se cumple por Liskov). Añade `disponible`,
  `momento_objetivo` (= anclaje + horizonte), `motivo`, `generado_en`.
  `version_modelo`=`modelo` ya existente, `confianza`=`data_completeness`.
  `ventana_datos` ahora también en calidad del aire.
- **Degradación.** `try/except` alrededor de cada `run_athena_query` /
  `run_neo4j_query` en los dos `_impl`; helper `_sin(motivo, …)`. Athena/Neo4j
  caídos, sin coincidencia, Gold sin lags, `.onnx` ausente → objeto con
  `disponible=False` + `motivo`, nunca excepción. Routers ramifican por
  `disponible` y vuelcan `motivo`.
- **Transporte.** `asistente/tests/test_mcp_transport.py`: `ClientSession`
  real sobre streams en memoria (`initialize`+`list_tools`+`call_tool` ×
  tools) y **subproceso `stdio`** (`python -m asistente.mcp_agent.server`,
  handshake por el pipe del SO). `test_mcp_hardening.py` (11) cubre el
  contrato + cada modo de fallo.
- **Docs.** `asistente/README.md` (tabla `RespuestaPrevision` + bloque
  `mcpServers`), `doc/FIL-15-mcp-server-hardening.md`.
- Suite: `asistente/` + `modelado/tests/test_ml07.py` → 101 passed.

## Contexto

El servidor MCP (`asistente/mcp_agent/server.py`, `mcp` 2.0.0) monta 7 tools
y se puede correr en `stdio` y montado en HTTP. Para presentarlo como capa
de producción faltan tres cosas: (1) verificación real del transporte con un
cliente MCP, (2) un envoltorio de respuesta homogéneo con procedencia, (3)
comportamiento definido cuando falta un modelo/tabla.

## Objetivo

Que cualquier cliente MCP (p. ej. Claude Desktop en `stdio`, o un cliente
HTTP) pueda descubrir y llamar las 7 tools, y que **toda** respuesta de una
tool de previsión lleve un envoltorio consistente.

## Alcance

1. **Transporte.** Probar `python -m asistente.mcp_agent.server` (stdio) con
   un cliente MCP real (script de `mcp` SDK o Claude Desktop) — `list_tools`
   + una `call_tool` de cada una. Documentar el `mcpServers` de ejemplo.
   Probar también la ruta HTTP montada en FastAPI.
2. **Envoltorio de respuesta.** Un modelo Pydantic común
   (`RespuestaPrevision` en `asistente/models/respuesta.py`) con: `valor`,
   `unidad`, `horizonte_h`, `clasificacion`, `generado_en`,
   `momento_objetivo`, `version_modelo` (del registry / nombre del `.onnx`),
   `ventana_datos` (rango de fechas de los lags usados), `confianza` o
   `n_lags_disponibles`, `fuente` ("modelo ONNX ML_07" / etc.). Aplicarlo a
   `calidad_aire_prevista`, `trafico_prevista` y, si existe,
   `afluencia_prevista`.
3. **Degradación.** Si falta el `.onnx`, o la Gold no tiene lags suficientes
   para `momento`, o Neo4j no responde: devolver un objeto con
   `valor=None` + `motivo` legible, nunca una excepción sin capturar. Tests
   para cada caso.
4. Esquemas de las tools: revisar que los docstrings/tipos que ve el cliente
   MCP son claros y sin jerga interna.

## Criterios de aceptación

- Un cliente MCP externo lista y llama las 7 tools contra la instancia real.
- Las tools `*_prevista` devuelven `RespuestaPrevision`; casos de fallo
  cubiertos por tests y devuelven objeto, no excepción.
- `asistente/README.md` + `doc/FIL-15-...md` con el `mcpServers` de ejemplo y
  el contrato de respuesta.

## Restricciones

- Sin auth/rate-limiting (queda para §7.5) — no es objetivo de este ticket.
