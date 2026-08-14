---
id: 26
slug: productores-lambda-handlers
title: Envolver cada productor programado en un handler Lambda de captura completa
status: failed
force: true
allow_infra_apply: false
branch: task/026-productores-lambda-handlers
pr_number: null
pr_url: null
attempts: 1
next_retry_at: null
last_error: 'InputTokens":12544435,"cacheCreationInputTokens":224231,"webSearchRequests":0,"costUSD":6.0018735,"contextWindow":1000000,"maxOutputTokens":64000,"canonicalModel":"claude-sonnet-5","provider":"firstParty"}},"permission_denials":[],"terminal_reason":"budget_exhausted","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subtype":"error_max_budget_usd","errors":["Reached
  maximum budget ($6)"],"type":"result","duration_ms":602271,"uuid":"7236a122-066c-46aa-8755-2c346182d4c6"}

  '
created_at: '2026-08-14T15:41:31+00:00'
updated_at: '2026-08-14T15:58:49.708321+00:00'
started_at: '2026-08-14T15:48:43.802111+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Segundo paso hacia producción, tras la 025 (BronzeWriter con soporte S3). Cada
productor (`ingesta/capturas/*.py`) se implementó deliberadamente acotado a una
**muestra pequeña** (tareas 002-024): sin bucle, sin escribir el dataset completo,
por la restricción de disco de esta EC2 que ya no aplica una vez el destino es S3.
Esta tarea prepara el código para ejecutarse como AWS Lambda, haciendo la captura
**completa** (no la muestra) y escribiendo en Bronze real vía `BronzeWriter`
(tarea 025). Todavía no se despliega nada (eso es la tarea 027/028) — es
exclusivamente código Python.

## Objetivo

Añadir un `lambda_handler(event, context)` a cada productor de la siguiente lista
(los que van a tener schedule — el resto, referencia estática o bajo demanda, se
queda como está, no los toques):

| Productor | Función |
|---|---|
| `trafico_madrid.py` (002) | ya tiene `capture_once`/bucle — solo falta el wrapper `lambda_handler` |
| `transporte_publico_madrid.py` (003/024) | captura completa (no limitada a `EMT_SAMPLE_SIZE`) |
| `bicimad.py` (004) | captura completa (no limitada a `BICIMAD_SAMPLE_SIZE`) |
| `aparcamientos_madrid.py` (005) | captura completa (no limitada a `MADRID_PARKING_SAMPLE_SIZE`) |
| `calidad_aire_madrid.py` (006) | captura completa |
| `meteorologia_madrid.py` (008) | captura completa |
| `ruido_madrid.py` (007) | captura completa (último día, todas las estaciones) |
| `afluencia_lugares_madrid.py` (012) | solo la parte de patrón típico (no la parte "vivo bajo demanda") |
| `aforos_peatones_bicicletas_madrid.py` (013) | comprobación de recurso nuevo + captura si aplica |
| `bluesky_menciones_madrid.py` (016) | solo `search_district_sweep`, no `search_place` |
| `agenda_eventos_madrid.py` (017) | captura completa de la agenda |
| `aemet_prevision_avisos.py` (018) | dos handlers separados o uno con `event` indicando `previsión`/`avisos` — decide y documenta |
| `cams_calidad_aire_madrid.py` (019) | captura completa |
| `cartelera_cines_madrid.py` (023) | solo `sweep_premieres`, no `fetch_cinema_showtimes` |

(022 no necesita handler propio: reutiliza el feed que ya descarga 017, según
documentó su propia tarea — no dupliques la captura.)

## Alcance concreto

1. Para cada productor de la tabla, localiza la función que ya hace el
   fetch+normalize **sin** el recorte a "unos pocos registros" (revisa cada
   módulo: en la mayoría el recorte ocurre solo al construir la muestra
   commiteada, no en el fetch en sí — confírmalo caso por caso, no lo asumas para
   todos).
2. Añade `lambda_handler(event, context)` que: llama a esa función de captura
   completa, construye un `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)`,
   y escribe el resultado con `write_batch`. Debe funcionar tanto si
   `BRONZE_BASE_PATH` es local (para poder probarlo en esta EC2 sin tocar S3) como
   `s3://...` (gracias a la tarea 025).
3. Si algún productor no separaba claramente "captura completa" de "captura
   muestra" y refactorizarlo es más invasivo de lo razonable para esta tarea,
   hazlo con criterio (es exactamente el tipo de refactor que esta tarea espera) —
   pero si alguno resultara bloqueado por algo imprevisto, documenta cuál y por qué
   en `doc/026-productores-lambda-handlers.md` y continúa con el resto; no dejes
   que uno bloquee toda la tarea.
4. Añade tests para cada `lambda_handler` nuevo (con dobles de red y de
   `BronzeWriter`/`boto3`, sin llamadas reales).
5. Actualiza `ingesta/README.md` señalando, para cada productor de la tabla, que ya
   tiene un `lambda_handler` listo para desplegar.

## Restricciones

- NO despliegues nada en AWS en esta tarea (ni Lambda, ni nada) — es solo código.
- NO ejecutes una captura completa real contra las fuentes en vivo si eso implicara
  volumen grande de datos hacia algún sitio (evita escribir localmente el dataset
  completo de fuentes grandes como tráfico/ruido/aforos; prueba la lógica con
  dobles/mocks, no con una ejecución real de producción).
- No toques los productores que no están en la tabla (009-011, 020, 021 son
  referencia estática; `search_place`/`fetch_venue_agenda`/`fetch_cinema_showtimes`
  quedan para que los use el futuro servicio del asistente bajo demanda, no un
  Lambda programado).

## Criterios de aceptación

- Cada productor de la tabla tiene un `lambda_handler` funcional y probado (con
  dobles, no red real).
- `doc/026-productores-lambda-handlers.md` deja constancia de cualquier productor
  que haya quedado sin resolver del todo, con el motivo.
- Todos los tests del proyecto siguen pasando.
