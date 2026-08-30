---
kind: fil
title: "opciones_movilidad y eventos_cercanos son las únicas 2 de 9 tools sin output_schema MCP (list[Model] no genera schema)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
---

## Resolución (2026-08-30)

Modelos contenedor en `asistente/models/herramientas.py`: `OpcionesMovilidad`
(`origen`/`destino`/`opciones: list[OpcionMovilidad]`) y `EventosCercanos`
(`lugar`/`radio_m`/`eventos: list[EventoCercano]`). Las funciones **públicas**
`tools.opciones_movilidad`/`tools.eventos_cercanos` devuelven el contenedor;
los `_*_impl` siguen devolviendo la lista (los ~15 tests que los llaman
directamente no se tocan). Routers leen `.opciones`/`.eventos`. Envolver un
`list[...]` en un `BaseModel` es lo que ya hacen las otras 7 tools.

`test_mcp_transport.py::test_list_tools_expone_las_9` ahora exige
`output_schema` con `properties` para **las 9** tools (servidor MCP real).
Arrancar el servidor ya no emite ningún `Cannot create schema`. Suite
`asistente/` + `tests/` → 113 passed. `doc/FIL-24-...md`.

> **Contexto**: encontrado en `VIKT_06` (recorrido end-to-end reproducible
> para la defensa, `doc/PLAN-REVISION-TFM.md`), levantando el servidor MCP
> real en `stdio` (`python -m asistente.mcp_agent.server`) con un
> `ClientSession` real y llamando cada tool, siguiendo el mismo patrón que
> `asistente/tests/test_mcp_transport.py` (`FIL_15`) pero además inspeccionando
> `list_tools()` en detalle. `FIL_15` (item 4 de su propio alcance,
> "esquemas de las tools: revisar que los... tipos que ve el cliente MCP son
> claros") ya declaraba esto en objetivo, pero no llegó a cubrirlo — el aviso
> es silencioso (nivel `INFO`, no falla ningún test existente).

## Qué está roto (verificado en vivo, servidor MCP real)

Al arrancar el servidor real (`stdio`), estos dos avisos aparecen siempre en
el log, para las únicas 2 de las 9 tools que devuelven una **lista** de un
modelo Pydantic en vez de un modelo Pydantic suelto:

```
Cannot create schema for type list[OpcionMovilidad] in opciones_movilidad:
PydanticUserError: `TypeAdapter[<class '...func_metadata.opciones_movilidadOutput'>]`
is not fully defined; you should define `<class '...opciones_movilidadOutput'>`
and all referenced types, then call `.rebuild()` on the instance.

Cannot create schema for type list[EventoCercano] in eventos_cercanos:
(mismo error, con eventos_cercanosOutput)
```

Verificado con un `ClientSession` real que esto **no es cosmético**: de las
9 tools listadas por `list_tools()`, exactamente estas 2 tienen
`output_schema=None` — las otras 7 (todas con tipo de retorno un modelo
Pydantic suelto, p. ej. `-> CalidadAireZona`) sí lo tienen:

| Tool | `output_schema` |
|---|---|
| afluencia_estimada | ✅ presente |
| afluencia_prevista | ✅ presente |
| calidad_aire | ✅ presente |
| calidad_aire_prevista | ✅ presente |
| trafico_cercano | ✅ presente |
| trafico_prevista | ✅ presente |
| disponibilidad_aparcamiento | ✅ presente |
| **opciones_movilidad** | ❌ **ausente** |
| **eventos_cercanos** | ❌ **ausente** |

**Causa raíz**: `asistente/mcp_agent/tools.py` — las únicas dos funciones con
anotación de retorno `-> "list[OpcionMovilidad]"` / `-> "list[EventoCercano]"`
(línea 948 y 1135). El SDK `mcp` 2.0.0 instalado (`func_metadata.py`) genera
internamente una clase envoltorio (`<tool>Output`) para poder anunciar un
`output_schema`, pero esa generación falla para un retorno `list[BaseModel]`
suelto (a diferencia de un `BaseModel` suelto, que sí funciona en las otras
7 tools) — el error de Pydantic ("not fully defined... call `.rebuild()`")
apunta a una referencia no resuelta en la clase envoltorio autogenerada.

## Por qué importa

- Un cliente MCP que dependa de `output_schema` para generar UI/validación
  tipada (no solo parsear el JSON del texto a mano) no tiene ninguna guía de
  forma para estas 2 tools — inconsistente con el resto de la API.
- Es exactamente lo que pedía el punto 4 del alcance de `FIL_15`
  ("esquemas de las tools: revisar que los... tipos que ve el cliente MCP
  son claros"), que se dio por cerrado sin cubrir este caso porque el aviso
  es `INFO`, no una excepción, y ningún test existente comprueba
  `output_schema` (solo el resultado de `call_tool()`).
- No afecta la funcionalidad real de las tools (ambas siguen devolviendo su
  JSON correctamente en el bloque de texto) — es puramente el contrato de
  schema anunciado, pero sí sesga la percepción de "capa de producción" que
  persigue `FIL_15`.

## Qué investigar / hacer (sin aplicar nada aquí)

1. Confirmar si es una limitación conocida del SDK `mcp` 2.0.0 con
   `list[BaseModel]` como retorno (revisar el changelog/issues del paquete
   instalado) o si hace falta una llamada explícita a
   `<Modelo>.model_rebuild()` en algún punto de import.
2. Workaround más simple si el SDK no lo soporta: envolver el retorno en un
   modelo contenedor de una sola clase (p. ej.
   `class OpcionesMovilidadOutput(BaseModel): opciones: list[OpcionMovilidad]`)
   en vez de devolver `list[...]` suelto — mismo patrón que ya funciona en
   las otras 7 tools (retorno de un `BaseModel` único). Requiere decidir si
   cambia el contrato de la tool (rompe clientes que ya parsean una lista
   plana) o si se mantiene la lista plana en el texto y solo se ajusta la
   anotación de tipo interna para el schema.
3. Añadir un test que falle si `output_schema` es `None` para cualquier
   tool nueva — así no vuelve a colarse en silencio (aprovechar
   `test_mcp_transport.py` de `FIL_15`, que ya levanta un `ClientSession`
   real).

## Restricciones

- No se ha tocado ningún código de `asistente/` en este ticket — solo
  verificación en vivo (`ClientSession` real sobre `stdio`, servidor real).

## Criterios de aceptación

- Las 9 tools tienen `output_schema` presente en `list_tools()`, verificado
  con un `ClientSession` real (no solo `mcp.list_tools()` en proceso).
- Test de regresión que cubra esto explícitamente.
- Documentado en `doc/FIL-24-...md` si aplica.
