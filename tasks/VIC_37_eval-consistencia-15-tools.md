---
kind: vic-eval
title: "Consistencia documental tras 14→15 tools MCP (consulta_grafo) y los nuevos endpoints"
owner: Claude (QA)
status: pending
created_at: "2026-09-09"
depends_on: [FIL_67]
---

## Contexto

Igual que `VIC_22` hizo el paso 9→10, hay que barrer las referencias al
número/lista de herramientas tras FIL_67 (14→15, `consulta_grafo`) y los
routers nuevos (`GET /consulta-grafo`).

## Alcance — solo verificación documental, sin cambios de lógica

1. **Recuento "N tools"** en todo el repo: `asistente/mcp_agent/server.py`
   (`description` + comentario "Las N tools sólo LEEN"),
   `asistente/README.md` (tabla de herramientas — ¿está `consulta_grafo`?
   ¿y `contexto_urbano` con sus campos nuevos?), `README.md` raíz,
   `doc/` que mencione el conteo, `notebooks/demo_madrono.ipynb`,
   `documents/Memoria_TFM*.docx` (para `VIC_38`).
2. **Tests que hardcodean la lista**: `test_mcp_tools.py::TOOL_FUNCTIONS`,
   `test_mcp_transport.py::_ESPERADAS` + `test_list_tools_expone_las_15` —
   ya actualizados; confirmar que no queda ningún `14`/`las 14` suelto.
3. **Routers**: `asistente/main.py` incluye `consulta_grafo.router`;
   `asistente/routers/` tiene el fichero; ¿`asistente/README.md` lista el
   endpoint `GET /consulta-grafo` como el resto?
4. **`grafo/consulta.py`** — ¿está documentado en `grafo/README.md` (nueva
   pieza del directorio) y en `infra/OPERACION.md` (runbook de consulta
   rápida al grafo)?
5. **`asistente/mcp_agent/server.py` `_INSTRUCCIONES`**: menciona las
   fuentes/uso de las tools — ¿conviene añadir una línea sobre
   `consulta_grafo` (plantillas de solo lectura) para el LLM cliente?

## Criterios de aceptación

- `grep -rn` por `"14 tool"`, `"14 herramientas"`, `"las 14"`, `"9 tools"`,
  etc. → 0 resultados obsoletos.
- Tabla de `asistente/README.md` = 15 filas, con `consulta_grafo` descrita.
- Cualquier doc desactualizado → PR de corrección (o `FIL_*` si es mayor).
