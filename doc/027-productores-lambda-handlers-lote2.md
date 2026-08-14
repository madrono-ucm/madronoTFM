# 027 — Handlers Lambda de captura completa, lote 2/3 (meteorología, ruido, afluencia, aforos, Bluesky)

## Qué se implementó

Continuación de la tarea 026 (mismo patrón, mismo motivo de reparto en tres
lotes: un primer intento con los 14 productores a la vez agotó el
presupuesto sin comitear nada). Se añadió `lambda_handler(event, context)` a
los 5 productores de la tabla del enunciado:

- `meteorologia_madrid.py` (008)
- `ruido_madrid.py` (007)
- `afluencia_lugares_madrid.py` (012)
- `aforos_peatones_bicicletas_madrid.py` (013)
- `bluesky_menciones_madrid.py` (016)

Cada handler llama a la función de captura **completa** del módulo (no la
muestra truncada de `capture_sample`) y escribe el resultado en Bronze real
vía `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)` — funciona
igual con `BRONZE_BASE_PATH` local o `s3://...` (tarea 025). No se desplegó
nada en AWS: es solo código, verificado con dobles en memoria (sin red ni
S3 reales).

Tabla completa (los 10 módulos de las tareas 026+027) en
`ingesta/README.md`, sección "Handlers Lambda (tareas 026/027, lotes 1/3 y
2/3)".

## Punto de partida: ya existía una implementación de referencia en la rama

El commit `3e3a112` de esta misma rama (creado en un intento anterior de la
tarea 026 que se pasó de alcance, y luego revertido para los módulos fuera
de ese alcance) ya contenía una implementación completa para estos 5
módulos, con las decisiones no triviales ya pensadas. Se revisó ese diff con
criterio (no se copió a ciegas: se leyó cada módulo actual primero para
confirmar que la función de captura completa que asumía el diff seguía
siendo la correcta caso por caso, tal como pedía el enunciado) y se aplicó
sin cambios sustanciales — coincidía con el estado real de los 5 módulos.

## Decisiones específicas por módulo

- **`meteorologia_madrid.py`**: `capture_all` reutiliza
  `fetch_raw_stations`/`fetch_raw_realtime`/`parse_stations`/
  `parse_realtime_entries`/`group_by_station`/`normalize_station_record` sin
  cambios, solo sin el recorte `[:sample_size]`; captura las ~25 estaciones
  de la red completa.
- **`ruido_madrid.py`**: `capture_all` captura todas las 31 estaciones del
  **último día disponible** (hasta 4 registros cada una, uno por periodo
  D/E/N/T) — el recorte "completa" aquí no es temporal (el CSV de origen es
  un histórico completo desde 2014, y traer todo el histórico no tendría
  sentido para un handler programado), sino de estaciones: todas, no solo
  `sample_stations`.
- **`afluencia_lugares_madrid.py`**: nueva función `capture_typical_patterns`
  y parámetro `include_live: bool = True` en `normalize_record`. El handler
  fuerza `include_live=False`, así que `live_pct` siempre viaja como `None`
  en el dataset `afluencia_lugares_patron_tipico`. Decisión explícita: la
  popularidad "en vivo" solo tiene sentido en el instante exacto de una
  pregunta puntual del usuario ("¿está muy lleno esto ahora?"), no en un
  barrido programado que produciría un dato ya obsoleto para cuando el
  asistente lo necesite — esa pregunta queda para una futura invocación bajo
  demanda de `resolve_place_id`/`fetch_populartimes`, no de este handler.
  Sigue dependiendo de `GOOGLE_MAPS_API_KEY` (ver bloqueo documentado en la
  tarea 012, sección "Sin bloqueos pendientes" más abajo).
- **`aforos_peatones_bicicletas_madrid.py`**: nueva función `capture_all`
  (todas las estaciones de ambos modos —peatones y bicicletas— del último
  día disponible, sin el recorte `sample_stations`/
  `sample_hours_per_station`) y nueva función `check_for_newer_resources`,
  que consulta el catálogo CKAN del dataset (`package_show`) y **solo avisa
  en los logs**, sin bloquear ni cambiar nada, si ya existe un recurso CSV
  más reciente que el configurado por defecto. Se justifica porque este
  dataset se actualiza solo trimestralmente (a diferencia de casi todos los
  demás productores del proyecto): un handler programado (p.ej. semanal)
  puede pasar mucho tiempo re-descargando el mismo último día ya capturado
  antes de que aparezca un recurso nuevo, así que vale la pena dejar
  constancia en los logs de cuándo conviene actualizar
  `MADRID_COUNTERS_PEDESTRIAN_URL`/`MADRID_COUNTERS_BICYCLE_URL` a mano. Un
  fallo de red al consultar CKAN se captura y solo genera un `logger.warning`
  (no interrumpe la captura real, que siempre usa la URL configurada).
- **`bluesky_menciones_madrid.py`**: el handler usa únicamente
  `search_district_sweep` (modo "barrido programado"), con la lista
  **completa** de distritos (`DEFAULT_DISTRICTS`, 21) y términos de evento
  (`DEFAULT_EVENT_TERMS`, 6) — no los subconjuntos truncados que usa
  `CaptureConfig.from_env()` por defecto para la muestra pequeña
  (`BLUESKY_SAMPLE_DISTRICTS`/`BLUESKY_EVENT_TERMS`). `search_place` (modo
  "bajo demanda") no tiene handler propio, tal como pedía el enunciado: está
  pensado para que lo invoque el futuro servicio conversacional en tiempo de
  consulta, no un schedule.

## Nombres de dataset Bronze

`meteorologia`, `ruido`, `afluencia_lugares_patron_tipico`,
`aforos_peatones_bicicletas`, `bluesky_menciones`. Ver la tabla completa en
`ingesta/README.md`.

## Sin bloqueos pendientes

Ninguno de los 5 productores de esta tarea quedó bloqueado por algo nuevo:

- `meteorologia_madrid.py` y `ruido_madrid.py` usan fuentes públicas de
  datos.madrid.es sin autenticación, ya desbloqueadas desde las tareas
  007/008.
- `aforos_peatones_bicicletas_madrid.py` igual, desde la tarea 013.
- `bluesky_menciones_madrid.py` usa un endpoint de lectura pública sin
  credenciales, desde la tarea 016.
- `afluencia_lugares_madrid.py` sigue dependiendo de una
  `GOOGLE_MAPS_API_KEY` que este entorno no tiene configurada (bloqueo ya
  documentado en la tarea 012, no nuevo de esta tarea): el código del
  handler queda completo y probado con dobles, listo para ejecutarse el día
  que exista esa credencial — no hace falta ningún cambio de código cuando
  eso ocurra.

## Restricciones respetadas

- Ningún test hace una llamada de red real ni escribe en S3: cada test
  nuevo en `ingesta/tests/test_lambda_handlers.py` sustituye la función de
  captura de más alto nivel del módulo (`capture_all`/
  `capture_typical_patterns`/`search_district_sweep`, más
  `check_for_newer_resources` en el caso de aforos) por un doble en
  memoria — esa función ya está probada por el `test_<módulo>.py`
  correspondiente.
- No se ejecutó ninguna captura completa real contra las fuentes en vivo.
- No se tocó ningún productor fuera de los 5 de esta tarea (en particular,
  no se adelantó nada de agenda de eventos/AEMET/CAMS/cartelera de cines,
  reservados para la tarea 028, aunque el commit de referencia `3e3a112`
  también los cubría).

## Suite de tests

`ingesta/tests/test_lambda_handlers.py` (ampliado, +7 tests: 5 handlers
básicos más 2 casos límite — `normalize_record` con `include_live=False` en
afluencia, y el manejo de fallo de red en `check_for_newer_resources` de
aforos). Suite completa del proyecto verificada tras el cambio: **242
tests** (235 previos + 7 nuevos), todos en verde
(`python3 -m unittest discover -s ingesta/tests -p "test_*.py"`).

## Relevante para tareas futuras

- La tarea 028 debe implementar `lambda_handler` para los 4 productores
  restantes (agenda de eventos, AEMET, CAMS, cartelera de cines), mismo
  patrón que aquí. El commit `3e3a112` de esta misma rama (visible en
  `git log`/`git show 3e3a112`) ya contiene una implementación de
  referencia para esos 4 módulos también, incluyendo decisiones ya pensadas
  para sus casos no triviales (AEMET: un único handler que decide
  `prevision`/`avisos` por `event["tipo"]`, para no duplicar despliegue de
  función/rol IAM entre las dos cadencias reales de esa fuente; cartelera:
  solo `sweep_premieres`, sin límite). No hace falta partir de cero ni
  volver a investigar esas decisiones — sí conviene revisar cada diff con
  criterio antes de reaplicarlo (confirmar caso por caso cuál es la función
  de captura completa real de cada módulo), en vez de copiarlo a ciegas,
  mismo criterio ya aplicado aquí.
- El siguiente paso natural tras completar 028 (fuera de esta tarea) sigue
  siendo escribir el Terraform que despliegue cada `lambda_handler` como
  función Lambda real con su EventBridge rule y el rol IAM correspondiente
  (ver notas ya dejadas en el doc de la tarea 026).
- El patrón `check_for_newer_resources` (aviso en logs sin bloquear la
  captura) introducido aquí para `aforos_peatones_bicicletas_madrid.py` es
  reutilizable: si una tarea futura encuentra otra fuente que se actualiza
  con muy poca frecuencia y publica un recurso nuevo con un identificador
  distinto cada vez (en vez de una URL estable), vale la pena aplicar el
  mismo criterio en vez de asumir que la URL configurada seguirá siendo la
  correcta para siempre.
