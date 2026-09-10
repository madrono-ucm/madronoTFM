---
kind: fil
title: "MCP consulta_grafo: descubrimiento de plantillas robusto + tuning de proximidad/nombres"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_67, FIL_70]
milestone: "M7"
target: "2026-09-20"
---

## Motivación

`consulta_grafo` (tool MCP nº 15, FIL_67) funciona pero en pruebas en vivo
con el chat (FIL_70) se ven dos problemas:

1. **El LLM adivina el `plantilla`** — prueba `estaciones_aire_cerca`,
   `aire_que_mide`, `estaciones`, `estaciones_calidad_aire`… La tool ya
   devuelve `plantillas_disponibles` cuando hay 0 filas, pero el modelo no
   siempre reintenta con un nombre válido y a veces se rinde con "no
   encontré nada".
2. **`aire_que_mide` para Retiro + ozono devuelve 0 filas** aunque la
   estación de aire "Retiro" (28079049) mide O₃. Sospechas: el filtro de
   proximidad cuelga de un nodo `:Lugar` ("Jardines de El Buen Retiro") y la
   `:EstacionMedida` de aire no está dentro del radio por `PROXIMO_A`; o el
   nombre del contaminante ("ozono" vs "O3"/"O₃"/código 8) no casa.

## Alcance

1. **Validación del `plantilla` en el schema** — que sea un `enum` en el
   `input_schema` de la tool (no un `str` libre), así Groq/OpenAI no puede
   mandar un valor inventado y, si lo hace, el error es inmediato y claro.
2. **Normalización de contaminante** — un mapa `ozono|o3|o₃|8 -> "O3"` (y
   equivalentes para NO₂, PM, etc.) en `asistente/neo4j_client.py` antes de
   construir la query. Cubrir con test.
3. **Revisar el radio y el anclaje de proximidad** de
   `estaciones_calidad_aire_que_miden_query` y de las demás `*_cerca`:
   ¿parten del `:Lugar` más cercano al texto, de un punto (lat/lon), del
   `:Barrio`? Documentarlo en el docstring y hacer que el radio por defecto
   (300 m) sea un parámetro con un valor sensato por plantilla.
4. **Diagnóstico en la respuesta** — cuando hay 0 filas, además de
   `plantillas_disponibles` incluir `radio_m` usado y el nodo de anclaje
   resuelto, para que el modelo (y una persona) entienda por qué.
5. **Tests en vivo** (marcados, opt-in con credenciales) — un puñado de
   pares (lugar, plantilla, contaminante) con conteo esperado > 0:
   Retiro/O₃, Chamberí/NO₂, Plaza Elíptica/PM10, líneas por parada de Sol,
   BiciMAD cerca de Callao.

## Verificación

- "¿qué estación de aire cerca de Retiro mide ozono?" en el chat devuelve
  la estación, no "no encontré nada".
- Suite `asistente/` verde; nuevos tests de normalización pasan sin red.

## Hecho (2026-09-10, rama `fil-72-consulta-grafo-robusto`)

1. **`plantilla` es un `enum`** — `consulta_grafo(plantilla: Literal[...])`;
   el schema MCP lo expone como `{"enum": [...8 nombres...]}`, así el LLM no
   puede inventarse un valor. Test que fija `Literal ⇄ _PLANTILLAS_GRAFO`.
2. **Normalización de contaminante** — `neo4j_client.normalizar_contaminante`:
   `ozono` / `O₃` / `8` / `dióxido de nitrógeno` / `pm25` / … → el código de
   Gold (`O3`, `NO2`, `PM2.5`, …). Se aplica **antes** de construir la query
   (`$contaminante IN e.contaminantes`, ya sin `toUpper()`). Era la causa más
   probable del "Retiro + ozono → 0 filas".
3. **Anclaje documentado** — el docstring de
   `estaciones_calidad_aire_que_miden_query` explica: parte del `:Lugar` por
   `CONTAINS`, sigue `PROXIMO_A` no dirigido, y **subir `radio_m` por encima
   de ~300 m no encuentra más** (no se cargaron esas relaciones) → si da 0,
   el problema es el nombre o el contaminante.
4. **Diagnóstico de 0 filas** — `ConsultaGrafo` gana `radio_m`,
   `contaminante_normalizado` y `lugares_candidatos` (los `:Lugar` cuyo
   nombre contiene el texto, vía `lugares_que_contienen_query`, sonda sin
   relaciones). `motivo` pasa a "0 resultados — ningún :Lugar contiene «X»;
   contaminante normalizado a «O3»; radio 300 m …".
5. **Tests en vivo** — `EnVivoTests` (opt-in con `NEO4J_URI`): Retiro/O₃,
   Chamberí/NO₂, Plaza Elíptica/PM10, BiciMAD/Callao, meteo/Retiro → `n_filas
   > 0`. Se salta sin credenciales.

Sin cambios en `_PLANTILLAS_GRAFO` (las 8 siguen). `pytest asistente/` →
251 passed, 1 skipped.
