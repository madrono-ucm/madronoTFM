# FIL-15 — Endurecer el servidor MCP: transporte, envoltorio, degradación

El servidor MCP (`asistente/mcp_agent/server.py`, `mcp` 2.0.0) ya montaba
8 tools en `stdio` y en HTTP. Faltaban tres cosas para presentarlo como capa
de producción: verificación real del transporte, un envoltorio de respuesta
homogéneo con procedencia, y comportamiento definido ante fallos de backend.

## 1. Envoltorio común — `RespuestaPrevision`

Nuevo modelo base en `asistente/models/respuesta.py`. `CalidadAirePrevista`
(`ML_09`) y `TraficoPrevista` (`FIL_13`) pasan a **heredar** de él en vez de
ser dos `BaseModel` sueltos con campos parecidos copiados a mano.

Se eligió herencia (subclase) en vez de renombrar los campos de dominio a un
esquema `{envoltorio, detalle}`: los dos modelos **ya** compartían de facto
`momento`/`horizonte_horas`/`valor_previsto`/`valor_actual`/`unidad`/
`nivel_previsto`/`data_completeness`/`modelo`/`ventana_datos`/`fuente_dataset`
— sólo faltaba factorizarlos. Los routers, tests y el `output_schema` que ve
el cliente MCP siguen construyéndose por kwargs, así que el cambio es
compatible; "las tools `*_prevista` devuelven `RespuestaPrevision`" se cumple
por Liskov (devuelven subclases).

Campos que añade el envoltorio sobre lo que ya había:

| Campo | Por qué |
|---|---|
| `disponible: bool` | Bandera única "¿hay cifra?" (`True` ⇔ `valor_previsto is not None`), en vez de que cada consumidor infiera de `nivel_previsto == "sin_datos"` |
| `momento_objetivo: datetime \| None` | Hora de pared a la que aplica la previsión = `momento` (anclaje) + `horizonte_horas`. `None` si no hubo anclaje |
| `motivo: str \| None` | Texto legible de por qué no hay cifra (backend caído, `.onnx` ausente, Gold sin lags…) |
| `generado_en: datetime` | Momento de construcción de la respuesta, distinto del anclaje (`momento`) |

`ventana_datos` ya lo ponía `trafico_prevista`; ahora `calidad_aire_prevista`
también (rango de fechas de los lags de la estación/contaminante elegidos).

`version_modelo` del ticket = el campo `modelo` ya existente
(`"<target>_h<H>.onnx (ML_07 / madrono-<target>-h<H>)"`); no se duplica.
`confianza` del ticket = `data_completeness` (0..1), ya existente.

## 2. Degradación elegante

`_calidad_aire_prevista_impl` y `_trafico_prevista_impl` envuelven ahora
**toda** llamada a `run_athena_query` / `run_neo4j_query` en `try/except` y
todas las ramas de "no hay datos" pasan por un helper local `_sin(motivo, …)`
que rellena el envoltorio. Casos cubiertos, cada uno con su `motivo` y sin
excepción hacia el cliente:

| Situación | Resultado |
|---|---|
| Athena lanza | `disponible=False`, `motivo="no se pudo consultar Gold en Athena: …"` |
| Neo4j lanza (solo tráfico) | `disponible=False`, `motivo="no se pudo consultar el grafo en Neo4j: …"` |
| Sin estación / lugar coincidente | `disponible=False`, `motivo` nombra el término buscado |
| Grafo OK pero Gold sin lecturas | `disponible=False`, `motivo` apunta a la tabla Gold |
| Serie horaria insuficiente para anclar | `disponible=False`, `motivo` sobre el anclaje |
| Falta el `.onnx` del horizonte | `disponible=False` pero **conserva** `valor_actual`/`ventana_datos`; `motivo` dice cómo generarlo |
| Todo OK | `disponible=True`, cifra + `momento_objetivo` + `ventana_datos` |

Los routers HTTP (`routers/calidad_aire_prevista.py`,
`routers/trafico_prevista.py`) ahora ramifican por `disponible` y vuelcan
`motivo` en la `explicacion` de la `RespuestaAsistente`.

## 3. Verificación del transporte

`asistente/tests/test_mcp_transport.py` (5 tests):

- **En memoria, protocolo real**: levanta `mcp._lowlevel_server.run(...)`
  sobre un par de streams y conecta un `ClientSession` de verdad —
  `initialize` + `list_tools` (las 8, con descripción e `input_schema`) +
  `call_tool` de `calidad_aire_prevista` y `trafico_prevista` (con backends
  mockeados en el mismo proceso; `.onnx` real). Comprueba
  `structured_content` con `disponible`, `valor_previsto`, `momento_objetivo`.
- **Degradación por el transporte**: `call_tool` con Athena que lanza →
  `is_error == False` y `structured_content["motivo"]` menciona Athena (el
  fallo no se propaga como error de protocolo).
- **`stdio` subproceso**: arranca `python -m asistente.mcp_agent.server` como
  proceso hijo, hace el handshake por el pipe del SO
  (`serverInfo.name == "madrono"`) y lista las 8 tools — exactamente lo que
  hace Claude Desktop.

`asistente/tests/test_mcp_hardening.py` (11 tests) cubre el contrato del
envoltorio y cada modo de degradación a nivel de tool (más rápido, sin
transporte).

## 4. Documentación

`asistente/README.md`: tabla de `RespuestaPrevision`, nota de degradación y
bloque `mcpServers` de ejemplo (`stdio`, con `env` para AWS/Neo4j) para
Claude Desktop.

## Pendiente / relacionado

- Sin auth ni rate-limiting (queda para §7.5, fuera de alcance del ticket).
- `FIL_14` (`afluencia_prevista`), si acaba siendo una tool servida por
  modelo, heredará de `RespuestaPrevision` sin cambios.
- El README de `asistente/` arrastra cifras viejas en otras secciones ("6
  tools", "32 tests") — corrección editorial en la pista `VIKT_*`.
