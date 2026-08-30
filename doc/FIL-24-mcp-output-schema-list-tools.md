# FIL-24 — `output_schema` para `opciones_movilidad` y `eventos_cercanos`

Encontrado en `VIKT_06` levantando el servidor MCP real en `stdio`: al
arrancar aparecían siempre dos avisos `INFO` y, de las 9 tools listadas por
`list_tools()`, exactamente estas dos tenían `output_schema = None`:

```
Cannot create schema for type list[OpcionMovilidad] in opciones_movilidad: PydanticUserError: ... not fully defined ...
Cannot create schema for type list[EventoCercano] in eventos_cercanos: ...
```

## Causa

Eran las únicas dos tools con anotación de retorno `-> list[BaseModel]`. El
SDK `mcp` 2.0.0 genera una clase envoltorio `<tool>Output` para anunciar el
`output_schema`; esa generación falla para un `list[BaseModel]` suelto (sí
funciona para un `BaseModel` suelto, que es lo que devuelven las otras 7).
Era exactamente el punto 4 del alcance de `FIL_15` ("esquemas de las tools:
revisar que los tipos que ve el cliente MCP son claros"), que se cerró sin
cubrir este caso porque el aviso es `INFO`, no una excepción.

## Solución

Dos modelos contenedor en `asistente/models/herramientas.py`:

- `OpcionesMovilidad`: `origen`, `destino`, `opciones: list[OpcionMovilidad]`.
- `EventosCercanos`: `lugar`, `radio_m`, `eventos: list[EventoCercano]`.

Las funciones **públicas** `tools.opciones_movilidad` / `tools.eventos_cercanos`
pasan a devolver el contenedor (envuelven el resultado del `_impl`
correspondiente, que sigue devolviendo la lista — así los ~15 tests que
llaman a `_*_impl` directamente no se tocan). Los routers leen `.opciones` /
`.eventos`.

Envolver la lista en un `BaseModel` con un campo `list[...]` es justo lo que
ya hacen las otras tools (p. ej. `TraficoCercano.estaciones:
list[EstacionTraficoCercana]`), y esas sí obtienen `output_schema`.

## Verificación

- `asistente/tests/test_mcp_transport.py::test_list_tools_expone_las_9`
  ahora comprueba, contra el servidor MCP real, que **las 9** tools tienen
  `output_schema` con `properties`.
- Arrancar el servidor real ya no emite ningún `Cannot create schema`.
- Suite `asistente/` + `tests/` → 113 passed.
