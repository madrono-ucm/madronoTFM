# 028 — Handlers Lambda de captura completa, lote 3/3 (agenda de eventos, AEMET, CAMS, cartelera de cines)

## Qué se implementó

Cierre de la serie de las tareas 026/027 (mismo patrón, mismo motivo de
reparto en tres lotes: un primer intento con los 14 productores a la vez
agotó el presupuesto sin comitear nada — ver doc/026). Se añadió
`lambda_handler(event, context)` a los 4 productores restantes de la tabla
del enunciado:

- `agenda_eventos_madrid.py` (017)
- `aemet_prevision_avisos.py` (018)
- `cams_calidad_aire_madrid.py` (019)
- `cartelera_cines_madrid.py` (023)

Cada handler llama a la función de captura **completa** del módulo (no la
muestra truncada de `capture_sample`) y escribe el resultado en Bronze real
vía `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)` — funciona
igual con `BRONZE_BASE_PATH` local o `s3://...` (tarea 025). No se desplegó
nada en AWS: es solo código, verificado con dobles en memoria (sin red ni
S3 reales).

Con este lote, los **14 productores programados** del proyecto (todos
salvo `agenda_recintos_madrid.py`, ver más abajo) tienen ya su
`lambda_handler`. Tabla completa en `ingesta/README.md`, sección "Handlers
Lambda (tareas 026/027/028, lotes 1/3, 2/3 y 3/3)".

## Punto de partida: ya existía una implementación de referencia en la rama

Igual que en la tarea 027, el commit `3e3a112` de esta misma rama (creado
en un intento anterior de la tarea 026 que se pasó de alcance, y luego
revertido para los módulos fuera de ese alcance) ya contenía una
implementación completa para estos 4 módulos, con las decisiones no
triviales ya pensadas. Se revisó ese diff con criterio — releyendo primero
el estado actual de cada uno de los 4 módulos (funciones de captura
completa, nombres de campos de `CaptureConfig`, docstrings) para confirmar
que seguía coincidiendo con lo que asumía el diff de referencia — y se
aplicó sin cambios sustanciales: coincidía exactamente con el estado real
de los 4 módulos, que no habían cambiado desde que se escribió ese commit.

## Decisiones específicas por módulo

- **`agenda_eventos_madrid.py`**: nueva función `capture_all` que reutiliza
  `fetch_municipal_events_raw`/`fetch_esmadrid_services_raw`/
  `normalize_municipal_event`/`normalize_esmadrid_event` sin cambios, solo
  sin el recorte `[:municipal_sample_size]`/`[:esmadrid_sample_size]` que sí
  aplican `fetch_municipal_events`/`fetch_esmadrid_events`: captura los
  ~669 eventos municipales completos y todos los `<service>` de la agenda
  de esMadrid.
- **`aemet_prevision_avisos.py`**: se implementa **un único**
  `lambda_handler`, no dos funciones separadas, que decide qué capturar
  según `event.get("tipo")` (`"prevision"` por defecto, o `"avisos"`).
  Justificación (documentada también en el propio docstring del módulo):
  ambas capturas comparten `CaptureConfig.from_env()` y la misma
  `AEMET_API_KEY`, así que dos EventBridge rules distintas —una por cada
  cadencia real que ya documentaba el módulo desde la tarea 018 (previsión
  "continua", avisos en los huecos de emisión preferentes)— pueden apuntar
  al mismo Lambda pasando un `tipo` distinto en su `input` configurado, sin
  duplicar el despliegue de función/rol IAM para lo que en el fondo es la
  misma integración con la misma credencial. Un `tipo` desconocido lanza
  `ValueError`; sin `AEMET_API_KEY` configurada lanza `RuntimeError` con el
  mismo mensaje que ya usaba `capture_sample`.
- **`cams_calidad_aire_madrid.py`**: wrapper directo sobre `fetch_forecast`,
  que ya descarga y normaliza la previsión completa configurada
  (`config.pollutants` x `config.leadtime_hours`) sin ningún recorte de
  muestra adicional que quitar. Sin `CAMS_ADS_API_KEY` configurada lanza
  `RuntimeError`, mismo criterio que `capture_sample`.
- **`cartelera_cines_madrid.py`**: el handler envuelve únicamente
  `sweep_premieres` (sin límite, a diferencia de la muestra que sí aplica
  `DEFAULT_PREMIERES_LIMIT`), tal como pedía explícitamente el enunciado.
  `fetch_cinema_showtimes` no tiene handler propio: queda para que lo
  invoque bajo demanda el futuro servicio conversacional (mismo criterio ya
  aplicado a `search_place` en `bluesky_menciones_madrid.py` o
  `fetch_venue_agenda` en `agenda_recintos_madrid.py`) — la cartelera
  horaria de un cine concreto solo tiene sentido cuando alguien pregunta
  por ese cine, no en un barrido programado.

## `agenda_recintos_madrid.py` (022) confirmado sin handler propio

Tal como adelantaba el enunciado, se verificó en el propio docstring del
módulo (líneas 14-27) que reutiliza por completo el mismo feed XML de
esMadrid que ya descarga `agenda_eventos_madrid.fetch_esmadrid_services_raw`,
filtrando en memoria por nombre de recinto — no hay ninguna captura de red
independiente que envolver en un handler aparte, así que no se añadió
ninguno. Documentado explícitamente en `ingesta/README.md` para que quede
claro que no es un olvido.

## Nombres de dataset Bronze

`agenda_eventos`, `aemet_prevision`/`aemet_avisos` (dos datasets desde un
único handler, ver arriba), `cams_calidad_aire`, `cartelera_cines_estrenos`.
Ver la tabla completa (los 14 módulos de las tareas 026+027+028) en
`ingesta/README.md`.

## Sin bloqueos pendientes

Ninguno de los 4 productores de esta tarea quedó bloqueado por algo nuevo:

- `agenda_eventos_madrid.py` usa fuentes de lectura pública sin
  autenticación, desbloqueadas desde la tarea 017.
- `cartelera_cines_madrid.py` usa SensaCine sin autenticación (zona gris de
  términos de uso ya documentada en la tarea 023, no nueva de esta tarea).
- `aemet_prevision_avisos.py` sigue dependiendo de `AEMET_API_KEY`, y
  `cams_calidad_aire_madrid.py` de `CAMS_ADS_API_KEY` — ambos bloqueos de
  registro manual ya documentados desde las tareas 018/019, no nuevos de
  esta tarea. El código de ambos handlers queda completo y probado con
  dobles (incluyendo el caso de credencial ausente, que lanza
  `RuntimeError` con el mismo mensaje explicativo que ya daba
  `capture_sample`), listo para ejecutarse el día que exista la credencial
  correspondiente — no hará falta ningún cambio de código cuando eso
  ocurra.

## Restricciones respetadas

- Ningún test hace una llamada de red real ni escribe en S3 ni en AWS: cada
  test nuevo en `ingesta/tests/test_lambda_handlers.py` sustituye la
  función de captura de más alto nivel del módulo (`capture_all`,
  `fetch_prediccion`/`fetch_avisos`, `fetch_forecast`, `sweep_premieres`)
  por un doble en memoria — esa función ya está probada por el
  `test_<módulo>.py` correspondiente.
- No se ejecutó ninguna captura completa real contra AEMET/CAMS ni contra
  ninguna otra fuente en vivo.
- No se capturó ningún secreto: los tests que necesitan una API key la
  fijan como una cadena ficticia (`"fake-key"`/`"fake-token"`) vía
  `patch.dict("os.environ", ...)`, nunca una credencial real.
- No se tocó ningún productor fuera de los 4 de esta tarea.

## Suite de tests

`ingesta/tests/test_lambda_handlers.py` (ampliado, +8 tests: uno para
`agenda_eventos_madrid.py`, cuatro para `aemet_prevision_avisos.py`
(previsión por defecto, avisos, `tipo` desconocido, API key ausente), dos
para `cams_calidad_aire_madrid.py` (captura completa, API key ausente) y
uno para `cartelera_cines_madrid.py` (sin límite en `sweep_premieres`).
Suite completa del proyecto verificada tras el cambio: **250 tests** (242
previos + 8 nuevos), todos en verde
(`python3 -m unittest discover -s ingesta/tests -p "test_*.py"`).

## Relevante para tareas futuras

- Con este lote se completa la serie 026/027/028: los 14 productores
  programados del proyecto tienen ya `lambda_handler`. El siguiente paso
  natural (tarea 029, ya anticipada en el propio enunciado) es escribir el
  Terraform que despliegue cada uno como función Lambda real con su
  EventBridge rule (cadencia por productor, ver notas ya dejadas en
  `ingesta/README.md` para AEMET/CAMS/aforos) y el rol IAM con permisos de
  escritura sobre el bucket Bronze (reutilizando
  `madrono-tfm-dev-ingestion-role` de la tarea 015 si aplica). Para
  `aemet_prevision_avisos.py` en concreto, esa tarea deberá crear **dos**
  EventBridge rules con `input` distinto (`{"tipo": "prevision"}` /
  `{"tipo": "avisos"}`) apuntando a la **misma** función Lambda, no dos
  funciones separadas — es la decisión de diseño de este lote.
  `agenda_recintos_madrid.py` no necesita ninguna regla propia: no tiene
  handler.
  - No confirmar que un diseño de referencia de una tarea previa (commit
    `3e3a112` u otro) sigue coincidiendo con el estado real del código
    antes de aplicarlo puede introducir bugs sutiles si el módulo cambió
    entre medias; en esta tarea sí se verificó módulo por módulo antes de
    aplicar el diff, y coincidía exactamente — pero es una comprobación que
    conviene repetir, no asumir, cada vez que se reutilice ese commit de
    referencia.
