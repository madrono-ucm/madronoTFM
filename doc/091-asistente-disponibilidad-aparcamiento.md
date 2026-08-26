# 091 — Asistente: implementar `disponibilidad_aparcamiento` (Prioridad 4)

## Contexto

Sesión interactiva, continuación directa de la tarea 090: al arreglar Gold
de `aparcamientos` se desbloqueó `disponibilidad_aparcamiento`, la `tool`
del asistente que hasta ahora levantaba `NotImplementedError` (ver
`NEXT_STEPS.md`, Prioridad 4). Mismo patrón que `calidad_aire` (tarea 079):
una sola tabla Gold vía Athena, sin grafo — la más simple de las `tools`
pendientes.

## Qué se hizo

- `asistente/mcp_agent/tools.py::_disponibilidad_aparcamiento_impl`: lee
  `gold.aparcamientos_por_parking_hora`, resuelve `zona` por coincidencia
  de texto contra `name`/`parking_id` (mismo criterio que `calidad_aire`
  con `station_name`/`station_id`). A diferencia de `calidad_aire` (peor
  caso entre estaciones coincidentes), varios aparcamientos que coinciden
  con `zona` representan capacidad real y aditiva -- `plazas_libres`/
  `plazas_totales` son la **suma**, no el peor caso.
- `asistente/models/herramientas.py::DisponibilidadAparcamiento`: extendido
  con `momento`/`hora`/`aparcamientos_consultados` (el esqueleto original de
  la tarea 044 solo tenía `zona`/`plazas_libres`/`plazas_totales`/
  `fuente_dataset` -- mismo criterio que la tarea 079 extendió
  `CalidadAireZona` al implementarla de verdad).
- `asistente/routers/disponibilidad_aparcamiento.py`: nuevo,
  `GET /disponibilidad-aparcamiento`, mismo patrón que
  `routers/calidad_aire.py`. Veredicto por ratio de plazas libres/totales
  (`>=15%` favorable, `>0%` con precaución, `0%` desfavorable).
- Registrado en `asistente/main.py` (router) — ya estaba registrado en
  `mcp_agent/server.py` (las 6 `tools`, incluidas las que levantaban
  `NotImplementedError`, ya se registraban desde la tarea 044).
- Tests: `DisponibilidadAparcamientoToolTests` (7 casos, mockeando Athena,
  mismo criterio que `CalidadAireToolTests`) +
  `test_disponibilidad_aparcamiento_router.py` (3 casos) + movido de la
  lista de `NOT_IMPLEMENTED_TOOL_FUNCTIONS`.

## Verificación real

Arrancado el servicio real (`AWS_PROFILE=madrono
AWS_DEFAULT_REGION=eu-west-1 uvicorn asistente.main:app`) contra la cuenta
AWS de este proyecto:

- `GET /disponibilidad-aparcamiento?zona=Plaza de Oriente` →
  `plazas_libres=189`, `plazas_totales=212`, `veredicto="favorable"`,
  `fiabilidad="alta"` — mismos valores exactos que la fila real de
  `gold.aparcamientos_por_parking_hora` consultada por separado con Athena
  en la tarea 090 (`'Plaza de Oriente', avg_free_spaces=189.0,
  total_spaces=212`).
- `GET /disponibilidad-aparcamiento?zona=Santo Domingo` →
  `plazas_libres=266`, `plazas_totales=333` — ídem, coincide con la fila
  real verificada en la tarea 090.
- `GET /disponibilidad-aparcamiento?zona=Zona Que No Existe En Madrid` →
  `fiabilidad="baja"`, `veredicto="con_precaucion"`, sin excepción.
- Verificado que la codificación UTF-8 de la respuesta es correcta a nivel
  de bytes (`\xc2\xab`/`\xc2\xbb` = «/» reales) — el `print()` de esta
  sesión local en Windows mostraba los acentos corruptos, pero era solo el
  `stdout` del terminal (cp1252), no un bug real del servicio.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform en esta tarea (mismo criterio
  que la tarea 044/079: se pospone hasta que se decida desplegar de verdad).
- No se ha tocado `opciones_movilidad`/`eventos_cercanos` (siguen con
  `NotImplementedError`, tareas de seguimiento separadas).
- Servicio local (`uvicorn`) parado al terminar la verificación.

## Relevante para tareas futuras

- Quedan 2 `tools` pendientes: `opciones_movilidad` (cruza 3 datasets) y
  `eventos_cercanos` — mismo patrón a seguir.
- El gap de `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` sin persistir en
  SSM (tarea 043/081) sigue sin resolver — no afecta a esta tool (no usa
  Neo4j), pero sigue bloqueando la verificación completa de
  `trafico_cercano`/`afluencia_estimada` en un entorno nuevo.
