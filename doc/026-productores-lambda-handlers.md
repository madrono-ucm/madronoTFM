# 026 — Handlers Lambda de captura completa para los productores programados

## Qué se implementó

Se añadió `lambda_handler(event, context)` a los 13 productores de la tabla
del enunciado (más el wrapper trivial de `trafico_madrid.py`, que ya hacía
captura completa desde la tarea 002). Cada handler: llama a la función de
captura **completa** del módulo (no la muestra truncada de `capture_sample`),
y escribe el resultado en Bronze real vía
`BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)` — funciona igual
con `BRONZE_BASE_PATH` local (probado en esta EC2) o `s3://...` (tarea 025).
No se despliega nada en AWS: es solo código, verificado con dobles.

Tabla completa de datasets y handler por módulo en `ingesta/README.md`,
sección "Handlers Lambda (tarea 026)".

## Refactors para separar "captura completa" de "captura muestra"

La mayoría de productores 003-019/023 solo tenían `capture_sample`, que
mezclaba fetch+normalize con el recorte a unos pocos registros para el
fixture versionado. Se añadió una función `capture_all` (o se reutilizó una
ya sin recorte) en cada uno, que hace el mismo fetch+normalize sin el
`[:sample_size]`: `transporte_publico_madrid.py`, `bicimad.py`,
`aparcamientos_madrid.py`, `calidad_aire_madrid.py`, `meteorologia_madrid.py`,
`ruido_madrid.py`, `aforos_peatones_bicicletas_madrid.py`,
`agenda_eventos_madrid.py`. `aemet_prevision_avisos.py` y
`cams_calidad_aire_madrid.py` ya tenían `fetch_prediccion`/`fetch_avisos`/
`fetch_forecast` sin recorte por defecto (el recorte solo vivía en
`capture_sample`), así que no hizo falta ningún refactor ahí: el handler
solo envuelve la función existente.

## Decisiones específicas por módulo

- **`afluencia_lugares_madrid.py`**: el handler (`capture_typical_patterns`)
  captura **solo el patrón típico**, no la popularidad "en vivo": se añadió
  el parámetro `include_live` a `normalize_record` para forzar `live_pct` a
  `None` en este modo. Razonamiento: la popularidad en vivo solo tiene
  sentido en el instante exacto de una pregunta del usuario ("¿está lleno
  ahora?"), no en un barrido programado que ya estaría obsoleto para cuando
  se consulte; esa pregunta puntual sigue siendo responsabilidad de una
  futura invocación bajo demanda, no de este handler.
- **`aforos_peatones_bicicletas_madrid.py`**: el handler primero llama a
  `check_for_newer_resources` (nueva función), que consulta el catálogo CKAN
  del dataset y **avisa por log** si ya existe un recurso CSV más reciente
  que el configurado por defecto — sin bloquear ni cambiar la URL usada. Se
  eligió este diseño porque el dataset se actualiza solo trimestralmente
  (ver docstring del módulo, tarea 013): sin este aviso, un schedule
  periódico (semanal) podría pasar meses re-descargando el mismo último día
  ya capturado antes sin que nadie note que hay una URL más reciente
  disponible. La captura en sí ("si aplica") siempre procede con la fuente
  configurada.
- **`bluesky_menciones_madrid.py`**: el handler usa solo
  `search_district_sweep`, con las listas **completas** de distritos (21) y
  términos de evento (6) — no los subconjuntos truncados que
  `CaptureConfig.from_env()` usa por defecto para la muestra pequeña
  (`BLUESKY_SAMPLE_DISTRICTS`/`BLUESKY_EVENT_TERMS`). `search_place` (modo
  "bajo demanda") no tiene handler, tal como pedía el enunciado.
- **`aemet_prevision_avisos.py`**: **un único** `lambda_handler`, que decide
  qué capturar según `event.get("tipo")` (`"prevision"` por defecto, o
  `"avisos"`), en vez de dos funciones separadas. Motivo: ambas capturas
  comparten `CaptureConfig`/`AEMET_API_KEY`; dos EventBridge rules (una por
  cada cadencia real — la previsión se actualiza "continuamente", los avisos
  en franjas horarias concretas) pueden invocar el mismo Lambda con un
  `input` distinto, sin duplicar despliegue de función/rol IAM.
- **`cartelera_cines_madrid.py`**: el handler usa solo `sweep_premieres`
  (estrenos de la semana, sin límite); `fetch_cinema_showtimes` no tiene
  handler, queda para uso bajo demanda del asistente, tal como pedía el
  enunciado.
- **`agenda_recintos_madrid.py`** (tarea 022) no tiene handler propio: como
  ya documentó su propia tarea, reutiliza el mismo feed que descarga
  `agenda_eventos_madrid.py` sin hacer ninguna petición HTTP nueva, así que
  capturar `agenda_eventos_madrid.py` ya cubre esos eventos.

## Nombres de dataset Bronze

Cada módulo obtiene una constante `DATASET_NAME` nueva (o, para
`aemet_prevision_avisos.py`, `DATASET_PREDICCION`/`DATASET_AVISOS`) que no
existía antes de esta tarea, porque hasta ahora ningún handler escribía en
Bronze particionado salvo `trafico_madrid.py`. Ver la tabla completa en
`ingesta/README.md`.

## Restricciones respetadas

- Ningún test hace una llamada de red real ni escribe en S3: cada test de
  `ingesta/tests/test_lambda_handlers.py` sustituye la función de captura de
  más alto nivel del módulo (`capture_all`, `fetch_forecast`,
  `sweep_premieres`...) por un doble en memoria — esa función ya está
  probada por el `test_<módulo>.py` correspondiente, así que estos tests
  solo verifican el código nuevo: que el handler llama a la captura
  correcta, escribe en Bronze (modo local, directorio temporal) con el
  dataset esperado, y devuelve un `dict` coherente.
- No se ejecutó ninguna captura completa real contra las fuentes en vivo
  (tráfico, ruido, aforos... podrían producir volumen grande); la lógica se
  verificó con dobles, no con una ejecución de producción.
- No se tocó ningún productor fuera de la tabla del enunciado
  (009-011, 020, 021 quedan como carga de referencia estática;
  `agenda_recintos_madrid.py` como se explica arriba).

## Sin bloqueos pendientes

A diferencia de otras tareas de este proyecto (018, 019, 012), esta tarea no
dependía de ninguna credencial nueva ni de resolver ningún registro: los
handlers de `aemet_prevision_avisos.py`/`cams_calidad_aire_madrid.py`/
`afluencia_lugares_madrid.py` heredan los mismos bloqueos ya documentados
por sus tareas originales (018, 019, 012 respectivamente) — el código queda
listo para ejecutarse el día que alguien complete esos registros, tal como
ya ocurría con `capture_sample`. Ningún módulo de la tabla quedó sin
resolver por esta tarea.

## Suite de tests

`ingesta/tests/test_lambda_handlers.py` (nuevo, 20 tests) cubre los 14
handlers. Suite completa del proyecto verificada tras el cambio: **250
tests** (230 previos + 20 nuevos), todos en verde.

## Relevante para tareas futuras

- El siguiente paso natural (fuera de esta tarea, mencionado como 027/028 en
  el enunciado) es escribir el Terraform que despliegue cada `lambda_handler`
  como función Lambda real con su EventBridge rule (cadencia por productor:
  ver notas de cadencia ya documentadas en `ingesta/README.md` para AEMET/
  CAMS) y el rol IAM con permisos de escritura sobre el bucket Bronze
  (reutilizando `madrono-tfm-dev-ingestion-role` de la tarea 015 si aplica).
- Los nombres de dataset (`DATASET_NAME` por módulo) son ahora la clave de
  partición real en Bronze (`<bucket>/<dataset>/fecha=.../hora=...`): una
  tarea futura de transformación Silver debe usarlos tal cual, no
  reinventar un nombre distinto por dataset.
- `afluencia_lugares_madrid.py` ahora produce dos "sabores" de captura desde
  el mismo módulo: `capture_sample` (fixture, con `live_pct`) y
  `capture_typical_patterns` (Lambda, sin `live_pct`). Si una tarea futura
  añade el servicio conversacional con la parte "bajo demanda" de esta
  fuente, debe usar `resolve_place_id`/`fetch_populartimes`/
  `normalize_record(..., include_live=True)` directamente, no este handler.
- `check_for_newer_resources` en `aforos_peatones_bicicletas_madrid.py` es
  best-effort (un log, no una alerta real): si una tarea futura quiere que
  esto dispare una notificación de verdad cuando aparezca un recurso nuevo,
  necesitaría un canal de alerta (SNS, etc.) que hoy no existe en el
  proyecto.
