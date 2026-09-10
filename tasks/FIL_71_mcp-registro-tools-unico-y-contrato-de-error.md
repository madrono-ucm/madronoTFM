---
kind: fil
title: "MCP server: una sola fuente de verdad para el registro de tools + contrato de error uniforme"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_67, FIL_70]
milestone: "M7"
target: "2026-09-20"
---

## Motivación

Los metadatos de las 15 tools MCP viven hoy en **tres sitios que se
desincronizan**:

1. `asistente/mcp_agent/tools.py` — las funciones reales + sus docstrings
   largos (para MCP/Claude Desktop) y el `@mcp.tool()` que registra el
   schema.
2. `asistente/mcp_agent/server.py` — `TOOL_FUNCTIONS` / `_ESPERADAS`
   (lista dura que los tests comparan).
3. `asistente/chat.py` — `_DESCRIPCIONES` (frases cortas para el
   tool-calling de Groq) **y** `_TOOLS_CHAT` (subconjunto que el chat
   expone) **y** la puerta de `_ejecutar_tool`.

FIL_70 encontró el fallo típico de esto: `consulta_grafo` estaba en
`_TOOLS_CHAT` (se ofrecía al modelo) pero `_ejecutar_tool` la rechazaba por
no estar en `_DESCRIPCIONES` → el modelo la llamaba y recibía "herramienta
desconocida" en bucle. Cada tool nueva obliga a tocar 3–4 sitios y a
actualizar 4–5 tests de conteo (`test_mcp_tools`, `test_mcp_transport`,
`test_list_tools_expone_las_15`, el texto "15 tools" de `server.py`…).

## Alcance

1. **Un registro único** — un módulo (`asistente/mcp_agent/registro.py` o
   similar) que declare, por tool: nombre, función, descripción corta,
   `expone_en_chat: bool`, `graph_first: bool`, y de dónde sale el schema
   (del propio `@mcp.tool`). `server.py`, `chat.py` y los tests leen de
   ahí. `_DESCRIPCIONES` / `_TOOLS_CHAT` / `TOOL_FUNCTIONS` / `_ESPERADAS`
   pasan a derivarse del registro (o desaparecen).
2. **Contrato de error uniforme** — hoy cada tool degrada a su manera
   (`{"error": ...}`, `disponible: false` + `motivo`, `n_filas: 0`…).
   Definir una forma común (p. ej. siempre `disponible: bool` + `motivo:
   str|None` + payload) y un helper que las tools usen. `_ejecutar_tool`
   en `chat.py` deja de inventar su propio `{"error": ...}` ad hoc.
3. **Test de coherencia** — un único test parametrizado sobre el registro:
   toda tool registrada es `callable`, tiene schema, y si `expone_en_chat`
   entonces `_ejecutar_tool` la ejecuta (no "desconocida"). Sustituye a los
   asserts de conteo repartidos.
4. **Doc** — `asistente/README.md`: la tabla de tools se genera del
   registro (o al menos se cita como fuente).

## Fuera de alcance

- Cambiar qué hace cada tool o su schema de parámetros.
- El subconjunto concreto que expone el chat (es decisión de producto, se
  queda como flag en el registro).

## Verificación

- Suite `asistente/` verde; los tests de conteo de tools desaparecen o se
  reducen a uno.
- Añadir una tool ficticia en una rama de prueba toca **un** sitio.

## Criterios de aceptación concretos (afinado 2026-09-10)

- `rg -n "_DESCRIPCIONES|_TOOLS_CHAT|TOOL_FUNCTIONS|_ESPERADAS" asistente/`
  solo devuelve coincidencias en `asistente/mcp_agent/registro.py` (+ su
  test). En `chat.py`, `server.py` y los demás tests: cero.
- Añadir una tool ficticia (`_ping`, devuelve `{"pong": True}`) en una rama
  de prueba = **1 fichero cambiado** (`registro.py`), suite verde, ningún
  test de conteo tocado, y aparece en `GET /mcp-server` list-tools.
- **Contrato de error** — toda tool devuelve un objeto que valida contra un
  modelo común (`Degradable`: `disponible: bool`, `motivo: str | None`, +
  payload tipado). Un test parametrizado sobre el registro fuerza el camino
  degradado de cada tool (mock de Athena/Neo4j que lanza) y afirma
  `disponible is False` + `motivo` no vacío + **sin excepción**.
- `_ejecutar_tool` de `chat.py` **nunca** construye su propio
  `{"error": ...}`: ante tool desconocida o fallo, devuelve/relanza la
  forma común. Test: pedirle a Groq (mockeado) una tool fuera del
  subconjunto → el hilo recibe un `motivo` legible, no un bucle.
- El bug de FIL_70 (`consulta_grafo` ofrecida pero rechazada) tiene un test
  de regresión explícito: toda tool con `expone_en_chat=True` en el
  registro **es ejecutable** por `_ejecutar_tool`.

## Prioridad y secuencia

**Alta.** Va **después de FIL_93** (docs) y **antes de FIL_72 y FIL_73**
(ambos consumen el contrato de error y el registro). Estimación ~1 día.
Objetivo: **2026-09-15**.
