# 026 — Handlers Lambda de captura completa, lote 1/3 (tráfico, EMT, BiciMAD, aparcamientos, aire)

## Qué se implementó

Se añadió `lambda_handler(event, context)` a los 5 productores de la tabla
del enunciado: `trafico_madrid.py`, `transporte_publico_madrid.py`,
`bicimad.py`, `aparcamientos_madrid.py`, `calidad_aire_madrid.py`. Cada
handler llama a la función de captura **completa** del módulo (no la
muestra truncada de `capture_sample`) y escribe el resultado en Bronze real
vía `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)` — funciona
igual con `BRONZE_BASE_PATH` local (probado en esta EC2) o `s3://...`
(tarea 025). No se despliega nada en AWS: es solo código, verificado con
dobles.

Tabla completa de datasets y handler por módulo en `ingesta/README.md`,
sección "Handlers Lambda (tarea 026, lote 1/3)".

## Refactor para separar "captura completa" de "captura muestra"

`trafico_madrid.py` ya hacía captura completa desde la tarea 002
(`capture_once`, sin recorte de muestra): su handler es un wrapper trivial.
Los otros 4 solo tenían `capture_sample`, que mezclaba fetch+normalize con
el recorte `[:sample_size]` para el fixture versionado. Se añadió una
función `capture_all` en cada uno (mismo fetch+normalize, sin el recorte):
`transporte_publico_madrid.py`, `bicimad.py`, `aparcamientos_madrid.py`,
`calidad_aire_madrid.py`.

## Corrección de alcance: un intento previo en esta misma rama ya cubría los 13 productores

Al empezar esta tarea, el worktree ya tenía un commit (`3e3a112`) que
implementaba `lambda_handler` para los **13 productores** de la tabla
completa del enunciado original (incluyendo meteorología, ruido, afluencia,
aforos, Bluesky, agenda de eventos, AEMET, CAMS y cartelera de cines) — el
mismo patrón de sobre-alcance que el propio enunciado de esta tarea advierte
explícitamente que ya falló una vez por agotar el presupuesto sin comitear
nada. Aquí sí llegó a comitearse, pero se sale del alcance que pide esta
tarea concreta (solo 5 productores; el resto está repartido en las tareas
027/028).

Se corrigió revirtiendo los cambios de `lambda_handler`/`capture_all` en los
8 módulos fuera de alcance (`meteorologia_madrid.py`, `ruido_madrid.py`,
`afluencia_lugares_madrid.py`, `aforos_peatones_bicicletas_madrid.py`,
`bluesky_menciones_madrid.py`, `agenda_eventos_madrid.py`,
`aemet_prevision_avisos.py`, `cams_calidad_aire_madrid.py`,
`cartelera_cines_madrid.py`) a su estado previo al commit `3e3a112`, y
recortando `ingesta/tests/test_lambda_handlers.py` y la sección nueva de
`ingesta/README.md` a los 5 módulos que sí corresponden a esta tarea. Los
cambios de los 5 módulos en alcance no se tocaron, ya estaban correctos.
Las tareas 027/028 pueden reimplementar el resto desde cero con su propio
presupuesto — no hace falta reutilizar ni recordar el trabajo revertido
aquí, que ya no existe en el árbol de trabajo.

## Decisiones específicas por módulo

- **`trafico_madrid.py`**: sin refactor, solo el wrapper `lambda_handler`
  sobre `capture_once` (ya escribía el lote completo en Bronze desde la
  tarea 002).
- **`transporte_publico_madrid.py`**: `capture_all` reutiliza
  `fetch_access_token`/`fetch_raw_arrivals`/`parse_records` sin cambios; la
  API ya devuelve todas las llegadas vigentes de una única parada
  (`EMT_STOP_ID`), así que "completa" aquí significa "sin el slicing
  `[:sample_size]`", no una fuente de datos distinta.
- **`bicimad.py`**: `capture_all` descarga las ~670 estaciones de la red
  completa (GBFS), sin recorte.
- **`aparcamientos_madrid.py`**: `capture_all` pide `GetDetailParking`
  (una llamada SOAP por aparcamiento) para todos los aparcamientos con
  ocupación en tiempo real del listado, no solo los primeros de la
  muestra; si una llamada de detalle falla, el registro se conserva con
  `total_spaces=None` en vez de descartarse (mismo criterio de tolerancia a
  fallos parciales que ya usaba `capture_sample`).
- **`calidad_aire_madrid.py`**: `capture_all` normaliza todos los registros
  estación+magnitud con lectura horaria válida ese día (24 estaciones x
  hasta ~18 magnitudes), sin recorte.

## Nombres de dataset Bronze

Cada uno de los 5 módulos obtiene una constante `DATASET_NAME` nueva
(`trafico_madrid.py` ya la tenía desde la tarea 002): `trafico`,
`transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`. Ver la
tabla completa en `ingesta/README.md`.

## Restricciones respetadas

- Ningún test hace una llamada de red real ni escribe en S3: cada test de
  `ingesta/tests/test_lambda_handlers.py` sustituye la función de captura de
  más alto nivel del módulo (`capture_once`/`capture_all`) por un doble en
  memoria — esa función ya está probada por el `test_<módulo>.py`
  correspondiente, así que estos tests solo verifican el código nuevo: que
  el handler llama a la captura correcta, escribe en Bronze (modo local,
  directorio temporal) con el dataset esperado, y devuelve un `dict`
  coherente.
- No se ejecutó ninguna captura completa real contra las fuentes en vivo
  (tráfico en particular podría producir volumen grande); la lógica se
  verificó con dobles, no con una ejecución de producción.
- No se tocó ningún productor fuera de los 5 de esta tarea — los 8
  revertidos (ver arriba) y el resto de la tabla original (009-011, 020,
  021 como carga de referencia estática; `agenda_recintos_madrid.py`) quedan
  intactos.

## Sin bloqueos pendientes

Ninguno de los 5 productores de esta tarea dependía de ninguna credencial
nueva ni de resolver ningún registro: los 5 ya tenían sus fuentes
desbloqueadas por tareas anteriores (002-006/024). Ningún módulo de esta
tarea quedó sin resolver.

## Suite de tests

`ingesta/tests/test_lambda_handlers.py` (nuevo, 5 tests) cubre los 5
handlers de este lote. Suite completa del proyecto verificada tras el
cambio: **235 tests** (230 previos + 5 nuevos), todos en verde
(`python3 -m unittest discover -s ingesta/tests -p "test_*.py"`).

## Relevante para tareas futuras

- Las tareas 027/028 deben implementar `lambda_handler` para el resto de
  productores programados (meteorología, ruido, afluencia, aforos, Bluesky,
  agenda de eventos, AEMET, CAMS, cartelera de cines) siguiendo el mismo
  patrón que aquí: `capture_all` sin recorte + `BronzeWriter` +
  `DATASET_NAME`. El commit `3e3a112` de esta misma rama (ya revertido para
  los módulos fuera de alcance, pero visible en `git log`/`git show
  3e3a112`) contiene una implementación completa de referencia para los 9
  módulos restantes, incluyendo decisiones ya pensadas para casos no
  triviales: `afluencia_lugares_madrid.py` (handler que captura solo el
  patrón típico, `live_pct` siempre `None`, vía un nuevo parámetro
  `include_live` en `normalize_record`), `aforos_peatones_bicicletas_madrid.py`
  (aviso best-effort de recurso CSV más reciente antes de capturar),
  `bluesky_menciones_madrid.py` (listas completas de distritos/términos, no
  la muestra truncada), `aemet_prevision_avisos.py` (un único handler que
  decide `prevision`/`avisos` por `event["tipo"]`, para no duplicar
  despliegue de función/rol IAM entre las dos cadencias reales de esa
  fuente) y `cartelera_cines_madrid.py` (solo `sweep_premieres`, sin
  límite). No es necesario partir de cero ni volver a investigar estas
  decisiones — sí conviene revisar cada diff con criterio antes de
  reaplicarlo, en vez de copiarlo a ciegas.
- El siguiente paso natural tras completar 027/028 (fuera de esta tarea) es
  escribir el Terraform que despliegue cada `lambda_handler` como función
  Lambda real con su EventBridge rule (cadencia por productor: ver notas de
  cadencia ya documentadas en `ingesta/README.md` para AEMET/CAMS) y el rol
  IAM con permisos de escritura sobre el bucket Bronze (reutilizando
  `madrono-tfm-dev-ingestion-role` de la tarea 015 si aplica).
- Los nombres de dataset (`DATASET_NAME` por módulo) son ahora la clave de
  partición real en Bronze (`<bucket>/<dataset>/fecha=.../hora=...`): una
  tarea futura de transformación Silver debe usarlos tal cual, no
  reinventar un nombre distinto por dataset.
- Lección de proceso para 027/028: antes de dar por buena la implementación,
  vale la pena comprobar que el alcance tocado en el árbol de trabajo
  coincide exactamente con la tabla de productores de la tarea concreta —
  un commit previo en la misma rama puede haberse pasado de alcance (como
  ocurrió aquí) y hace falta revertir la parte sobrante antes de continuar,
  no solo añadir lo que falta.
