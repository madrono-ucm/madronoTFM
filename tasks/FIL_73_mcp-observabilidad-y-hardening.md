---
kind: fil
title: "MCP server: observabilidad de tool-calls, test de integración con cliente real, y frescura de datos"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_62, FIL_70]
milestone: "M7"
target: "2026-09-23"
---

## Motivación

El servidor MCP y el `/chat` que lo orquesta funcionan, pero cuando algo
falla en producción (EC2 pública) hoy hay poca visibilidad, y hay dos
riesgos conocidos sin cubrir:

- El bug `421 Misdirected Request` (protección DNS-rebinding del SDK MCP,
  arreglado en `main.py` declarando `allowed_hosts`) se encontró **a mano**
  probando un cliente MCP real; los tests con streams en memoria no pasan
  por esa comprobación. No hay red de seguridad para el siguiente de ese
  tipo.
- El pipeline de datos está **congelado desde 2026-08-30**. Las tools
  filtran por una ventana de 14 días (`_recent_date_filter()`), así que cada
  vez más consultas devuelven "sin datos" en silencio. El usuario no
  distingue "no hay estación ahí" de "no hay datos recientes".

## Alcance

1. **Logging estructurado de tool-calls** — en `asistente/chat.py`
   (`_ejecutar_tool`) y/o en el registro (FIL_71): por cada llamada, un log
   con `tool`, args (recortados), `duracion_ms`, `ok`/error, `n_filas` si
   aplica. Nivel INFO. Sin PII (no hay, pero dejarlo dicho).
2. **Métrica de latencia del LLM** — `_completar` ya reintenta; añadir
   `duracion_ms` y nº de reintentos al log. Contador simple de 429 servidas
   (para saber si el tier gratuito se queda corto).
3. **Test de integración con un cliente MCP de verdad** —
   `mcp.client.streamable_http` contra la app montada (TestServer / puerto
   efímero), que liste tools y llame a una tool sencilla. Pilla la clase de
   bug del `421`. Marcado si hace falta (arranca un servidor).
4. **Frescura de datos en la respuesta** — un helper común (encaja con el
   contrato de error de FIL_71): cuando una tool filtra por fecha y no hay
   filas en la ventana, devolver `motivo="sin datos en los últimos N días
   (pipeline pausado desde AAAA-MM-DD)"` en vez de un `n_filas: 0` mudo. El
   `_SYSTEM_PROMPT` del chat ya dice "si no hay datos, dilo"; darle el
   material para decirlo bien.
5. **Rate-limit uniforme** — que el 429 del LLM y el (hipotético) 429 de
   una fuente upstream se traten igual y se comuniquen igual al usuario
   ("vuelve a intentarlo en un momento"), no con trazas crudas.

## Fuera de alcance

- Descongelar el pipeline / reingesta (otro track).
- Métricas a CloudWatch / dashboards (esto es solo logging estructurado a
  stdout, que ya recoge el runner del servicio).

## Verificación

- Un `POST /chat` deja en el log una línea por tool-call con duración.
- El test de integración MCP falla si se revierte el fix de `allowed_hosts`.
- "calidad del aire en Vicálvaro" (zona sin datos recientes) responde
  distinguiendo "sin datos recientes" de "zona desconocida".

## Criterios de aceptación concretos (afinado 2026-09-10)

- **Logging** — un `POST /chat` que dispara 2 tool-calls emite exactamente
  2 líneas INFO que casan con
  `tool=\S+ dur_ms=\d+ ok=(True|False)( filas=\d+)?`. Args recortados a N
  chars. Un test con `caplog` lo comprueba.
- **Latencia LLM** — cada respuesta de `_completar` añade al log
  `llm_dur_ms=\d+ reintentos=\d+`; un contador de 429 servidas acumulado en
  proceso, expuesto en `GET /health` como `llm_429_total`.
- **Test de cliente MCP real** — `asistente/tests/test_mcp_cliente_real.py`:
  levanta la app montada en un puerto efímero, se conecta con
  `mcp.client.streamable_http`, lista tools (== `len(_ESPERADAS)`) y llama a
  `avisos_meteo`. **Revertir `allowed_hosts` en `main.py` hace fallar este
  test con 421** (aserción explícita del código de estado). Marcado
  `@pytest.mark.integracion` si arranca servidor.
- **Frescura** — helper `motivo_sin_datos(ventana_dias, desde)` (encaja con
  el `Degradable` de FIL_71). "calidad del aire en Vicálvaro" (zona real,
  sin datos en ventana) → `motivo` contiene `"sin datos en los últimos 14
  días"` y una fecha; una zona inexistente → `motivo` distinto
  (`"no se encontró la zona"`). Test que afirma que los dos `motivo` no son
  iguales.
- **Rate-limit uniforme** — el 429 de Groq y un 429 upstream simulado
  producen **el mismo string** al usuario (`"vuelve a intentarlo en un
  momento"`), nunca una traza. Un test parametriza ambos orígenes.

## Prioridad y secuencia

**Media-alta.** Después de **FIL_71** (comparte `Degradable` y el registro).
Puede solaparse con FIL_72. Estimación ~1 día. Objetivo: **2026-09-17**.
