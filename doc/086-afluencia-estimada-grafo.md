# 086 — Especificación: afluencia estimada vía grafo (sustituto de Google Maps)

**Esta tarea es solo la especificación, sin implementar** — decisión
explícita tomada con el usuario el 25/8 (ver `doc/083-investigacion-google-
maps-arquitectura.md`): documentar el diseño con suficiente detalle para
que una sesión de seguimiento lo construya sin tener que releer toda la
investigación previa.

## Por qué esta forma, y no otra

`afluencia_lugares`/Google Maps daba, para un lugar, un patrón de
popularidad estimado (`live_pct`, `typical_by_hour`). La tarea 083
demostró que reproducir eso con datos reales cuesta dinero siempre. En vez
de imitar la forma exacta del dato de Google, esta especificación propone
una señal distinta pero con el mismo propósito ("¿está concurrido este
sitio ahora?"), construida sobre datos ya ingeridos a coste 0, siguiendo el
mismo patrón que `trafico_cercano` (tarea 081): resolver `lugar` contra el
grafo, seguir `PROXIMO_A` hasta sensores cercanos, leer su último valor en
Gold.

## Hallazgo de esta tarea: el grafo NO tiene hoy los nodos que hacen falta

Revisando `grafo/README.md` (tabla "Orígenes por tipo de nodo", tareas
067/070/071) antes de escribir esta especificación: los `:EstacionMedida`
cargados hoy vienen solo de `trafico`, `calidad_aire` y `ruido` Gold.
**`aforos_peatones_bicicletas` — la fuente más directa y precisa para
"cuánta gente hay físicamente aquí" (son contadores oficiales de peatones y
bicicletas) — no está en el grafo.** Tampoco lo están `agenda_eventos`/
`agenda_recintos`.

Esto cambia el alcance de "solo escribir una tool nueva" a **dos fases
secuenciales**, documentadas por separado más abajo:

- **Fase A** (prerrequisito, toca `grafo/`): añadir
  `aforos_peatones_bicicletas` como nuevo origen de `:EstacionMedida`,
  siguiendo exactamente el patrón ya existente para trafico/calidad_aire/
  ruido — y recargar la instancia real de Neo4j con los nuevos nodos
  (`MERGE`, no destructivo sobre lo ya cargado).
- **Fase B** (la tool en sí, toca `asistente/`): `afluencia_estimada`,
  construida sobre el grafo ya extendido por la Fase A.

Sin la Fase A, la Fase B solo podría ofrecer las mismas señales que
`trafico_cercano` ya expone (tráfico, BiciMAD) — señal débil y redundante,
no una mejora real sobre lo que había.

## Fase A — extender `grafo/` con `aforos_peatones_bicicletas`

Réplica exacta del patrón ya usado para `ruido` (el más reciente de los
tres orígenes actuales de `:EstacionMedida`, tarea 067/069):

1. `grafo/extract.py`: nueva función `fetch_estaciones_aforos_peatones_
   bicicletas()`, mismo patrón que `fetch_estaciones_ruido` — consulta
   Athena sobre el Gold real de este dataset (confirmar el nombre exacto de
   la tabla Gold en `procesamiento/silver_gold/aforos_peatones_bicicletas/`
   antes de escribir la query; **no está entre las 3 tablas Gold rotas
   conocidas** — `aparcamientos`/`cartelera_cines_estrenos`/
   `afluencia_lugares`, ver `NEXT_STEPS.md` — así que se espera que tenga
   datos reales).
2. `grafo/nodos.py`: `estacion_medida_from_aforos_peatones_bicicletas_gold`
   / plural, mismo contrato que las 3 funciones equivalentes ya existentes
   (`id` = `"aforos_peatones_bicicletas:<id_origen>"`, `tipo=
   "aforos_peatones_bicicletas"`).
3. `grafo/cargar_grafo.py`: añadir esta lista a la unión de nodos con
   ubicación que ya alimenta `relaciones.ubicado_en`/`proximo_a` — no hace
   falta tocar `relaciones.py` (genérico sobre cualquier nodo con
   `ubicacion`+`tipo`).
4. Tests: replicar `test_extract.py`/`test_nodos.py` de `ruido` para el
   nuevo origen (mock de Athena, sin conexión real).
5. **Recarga real de Neo4j**: ejecutar `cargar_grafo.py` contra la
   instancia real (credenciales de SSM, `eu-west-1`) — es un `MERGE`, no
   borra nada de lo ya cargado (9327 nodos/41031 relaciones de la tarea
   080 quedan intactos), pero es una escritura real contra la instancia de
   producción del grafo. Verificar después con Cypher real
   (`MATCH (e:EstacionMedida {tipo: "aforos_peatones_bicicletas"}) RETURN
   count(e)`) que los nodos nuevos existen, y con una consulta `PROXIMO_A`
   real que al menos un `:Lugar` conocido tiene ahora una estación de
   aforos cercana.

## Fase B — `afluencia_estimada(lugar, radio_m=300.0, momento=None)`

Mismo esqueleto que `trafico_cercano` (`asistente/mcp_agent/tools.py`,
`asistente/neo4j_client.py`, `asistente/routers/`):

1. Resolver `lugar` contra `:Lugar` en el grafo (coincidencia de texto,
   igual que `trafico_cercano`).
2. `PROXIMO_A` hasta `:EstacionMedida {tipo: "aforos_peatones_bicicletas"}`
   dentro de `radio_m` — señal primaria.
3. Señales secundarias, mismo patrón de cruce: `:ParadaTransporte {tipo:
   "bicimad"}` (ocupación) y `:EstacionMedida {tipo: "trafico"}`
   (intensidad, ya usado por `trafico_cercano` — reutilizar, no duplicar
   la consulta) dentro del mismo radio.
4. Si `aparcamientos` (Prioridad 2 de `NEXT_STEPS.md`) ya está arreglado
   para cuando se implemente esto, añadir su ocupación como cuarta señal;
   si no, omitirla sin error (mismo criterio que `calidad_aire`/
   `trafico_cercano` con datos ausentes: `resumen="sin_datos"` parcial, no
   excepción).
5. Combinar las señales en un `nivel_estimado` simplificado
   (`bajo`/`medio`/`alto`), documentando la fórmula como aproximación
   deliberada — mismo criterio que `indice_calidad` de `calidad_aire`
   (tarea 079) y `resumen` de `trafico_cercano` (tarea 081): una etiqueta
   simple con su limitación documentada, no un índice oficial.
6. `agenda_eventos`/`agenda_recintos` como indicador anticipado queda
   **fuera del alcance de esta tool** — no están en el grafo (ver
   hallazgo de arriba) y añadirlos sería una tercera fase; mencionar en
   `RespuestaAsistente.explicacion` cuando no se dispone de este dato, para
   que quede trazable la limitación.
7. Registrar como la 7ª tool del agente MCP (`asistente/mcp_agent/
   server.py`), sustituyendo la entrada `afluencia_prevista` en la tabla
   de `asistente/README.md` (que pasa de `NotImplementedError` a esta
   implementación real).

## Nombre: por qué no se reutiliza `afluencia_prevista`

Se renombra a `afluencia_estimada` porque `afluencia_prevista` (nombre del
esqueleto original, tarea 044) sugiere previsión temporal (`typical_by_hour`
de Google) — esta tool da un estado estimado del momento actual/consultado
a partir de sensores reales, no una previsión estadística histórica. Si una
tarea futura quiere añadir previsión real (p. ej. a partir de series
históricas de `aforos_peatones_bicicletas` Gold), sería una extensión de
esta misma tool o una nueva, no un motivo para revertir este nombre.

## Relevante para tareas futuras

- La Fase A es un prerrequisito real, no opcional — sin ella, la Fase B no
  aporta señal nueva sobre lo que `trafico_cercano` ya da.
- Confirmar el nombre exacto de la tabla Gold de `aforos_peatones_
  bicicletas` (`procesamiento/silver_gold/aforos_peatones_bicicletas/`)
  antes de escribir la query de `extract.py` — no verificado en esta
  tarea, que es solo especificación.
- Si la Prioridad 1 de `NEXT_STEPS.md` (drift de Terraform) no se ha
  reconciliado antes de implementar esto, verificar primero que el código
  de `aforos_peatones_bicicletas` realmente desplegado coincide con
  `main` — la tarea 083 encontró que esa garantía no existe hoy.
