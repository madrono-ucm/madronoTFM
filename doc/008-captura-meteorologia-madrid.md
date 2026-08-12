# 008 — Captura de datos meteorológicos de Madrid (muestra)

## Qué se implementó

Séptimo productor de datos de la Fase 1 (Ingesta), con el mismo alcance
reducido que las tareas 003-007 (captura puntual de muestra, no productor
continuo — la infraestructura AWS de la tarea 001 sigue sin aplicarse):

- `ingesta/capturas/meteorologia_madrid.py`: descarga las lecturas horarias
  en tiempo real de la red de ~25 estaciones meteorológicas del
  Ayuntamiento de Madrid y, para poder resolver nombre/ubicación de cada
  estación, su catálogo de estaciones, los normaliza a un esquema mínimo
  (un registro por estación, con temperatura, humedad, viento, presión,
  radiación y precipitación como columnas), y guarda una **muestra pequeña**
  (5 estaciones por defecto, configurable) en un fichero fijo — sin bucle,
  sin `--interval-seconds`, sin escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/meteorologia_madrid_sample.json`: la muestra
  pequeña commiteada como fixture (5 estaciones).
- `ingesta/tests/test_meteorologia_madrid.py` +
  `ingesta/tests/fixtures/meteorologia_realtime_sample.json` +
  `ingesta/tests/fixtures/meteorologia_estaciones_sample.csv`: tests con
  `unittest` (sin red) que verifican el agrupado por estación, la
  combinación de varias magnitudes en un único registro, el caso de una
  magnitud no reconocida (se ignora sin fallar), una estación sin ninguna
  hora válida (se descarta), y una estación sin metadatos conocidos en el
  catálogo, y que la muestra commiteada cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida y por
  qué no AEMET, formato real encontrado, variables de entorno, esquema, y
  la nota sobre el acceso en vivo desde este entorno).

## Fuente elegida y por qué: datos.madrid.es, no AEMET

El objetivo de la tarea sugería tanto la red de estaciones meteorológicas
del Ayuntamiento de Madrid (datos.madrid.es, sin autenticación) como AEMET
OpenData (requiere una API key gratuita con registro) como alternativa. Se
eligió la fuente municipal: cubre el objetivo completo (temperatura,
humedad, viento, precipitación, y además presión y radiación solar/UV) sin
necesidad de ningún registro ni credencial, evitando así el mismo tipo de
bloqueo manual (verificación por email) que impidió una captura real en
vivo en la tarea 003 (transporte público, API EMT MobilityLabs).

Dataset "Datos meteorológicos. Datos en tiempo real" (id
`300392-0-meteorologia-tiempo-real`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300392-0-meteorologia-tiempo-real),
combinado con "Datos meteorológicos. Estaciones de control" (id
`300360-0-meteorologicos-estaciones`) para los metadatos de cada estación
(nombre, dirección, coordenadas WGS84 ya en decimal, altitud).

## Formato real encontrado: mismo backend que calidad del aire

Se confirmó descargando ambos recursos en vivo y contrastándolo con el PDF
"Intérprete de ficheros de datos meteorológicos horarios – diarios y tiempo
real" (que el propio dataset enlaza) que este dataset usa **el mismo
backend "bdca"** (Servicio de Calidad del Aire del Ayuntamiento) que
`calidad_aire_madrid.py` (tarea 006): un registro por combinación
estación+magnitud+día, con las 24 lecturas horarias del día embebidas en
columnas `H01`..`H24`/`V01`..`V24`. A diferencia del JSON de calidad del
aire, aquí no hay campo `PUNTO_MUESTREO`: el código de estación es
directamente el campo `ESTACION` (p.ej. `"102"`), que ya coincide con la
columna `CÓDIGO_CORTO` del catálogo de estaciones, así que no hizo falta
reconstruirlo a partir de otro campo compuesto.

Magnitudes disponibles (Anexo II del PDF): `80` radiación ultravioleta,
`81` velocidad de viento, `82` dirección de viento, `83` temperatura, `86`
humedad relativa, `87` presión barométrica, `88` radiación solar, `89`
precipitación. No todas las ~25 estaciones miden todas las magnitudes (el
catálogo marca con `X` cuáles sí).

## Decisión relevante: un registro por estación, no por magnitud

A diferencia de `calidad_aire_madrid.py` (un registro de salida por
combinación estación+magnitud), aquí `normalize_station_record` combina
**todas las magnitudes de una misma estación en un único registro**, con
`temperature_c`, `humidity_pct`, `wind_speed_ms`, `wind_direction_deg`,
`pressure_mb`, `solar_radiation_wm2`, `uv_radiation_mwm2` y
`precipitation_lm2` como columnas (`null` si esa estación no mide esa
magnitud). Se decidió así porque el propio objetivo de la tarea pide
explícitamente un esquema con "temperatura, humedad, viento,
precipitación" como campos de un mismo registro — un registro por
estación es el resultado más directamente utilizable para ese objetivo,
frente al registro por magnitud de calidad del aire (donde cada lectura es
un valor de un contaminante concreto, sin relación natural de "un registro
por punto en el tiempo y lugar").

`measured_at` se calcula como la hora válida más reciente **entre todas
las magnitudes de la estación** (no una por campo): en la práctica, una
misma estación actualiza todas sus magnitudes a la vez (verificado con
datos reales: todas las magnitudes de una estación comparten las mismas
horas válidas/no válidas ese día), así que un único timestamp por registro
es razonable y más simple que uno por campo.

## Captura real en vivo

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/meteorologia_madrid_sample.json`) son 5
estaciones reales (J.M.D. Moratalaz, E.D.A.R. La China, Centro Mpal. De
Acústica, J.M.D. Hortaleza, Peñagrande), descargadas ejecutando
`python3 -m ingesta.capturas.meteorologia_madrid` tal cual contra ambos
recursos públicos durante esta sesión — no son datos de ejemplo generados
a mano. De las 25 estaciones que reportaron datos en el momento de la
captura, la mayoría solo tenían 2 horas válidas ese día (H01/H02), lo que
sugiere una actualización reciente de la red o un reinicio de sensores —
no afecta a la validez del esquema, solo a cuántas horas del día tenían
dato disponible en ese instante.

## Otras decisiones de diseño (por qué)

- **Magnitudes no reconocidas se ignoran sin fallar**: si la fuente
  añadiera en el futuro un código de magnitud no presente en
  `MAGNITUDES`, `normalize_station_record` lo descarta silenciosamente en
  vez de lanzar una excepción — mismo criterio de robustez que
  `calidad_aire_madrid.py` con `magnitude_abbr`/`unit` a `null` para
  magnitudes desconocidas, adaptado aquí a "ignorar el campo" porque el
  esquema de salida es de columnas fijas, no de un campo `value` genérico.
- **Estación sin ninguna hora válida se descarta** (`normalize_station_record`
  devuelve `None`): igual que en calidad del aire (tarea 006), si ninguna
  magnitud de una estación tiene dato válido ese día, el registro no
  aportaría ningún valor meteorológico.
- **`station_id` es el código completo del catálogo** (`CÓDIGO`, p.ej.
  `"28079102"`), no el código corto que usa el feed de tiempo real
  (`CÓDIGO_CORTO`, p.ej. `"102"`) — mismo formato de `station_id` que
  `calidad_aire_madrid.py`, para que sea consistente entre fuentes que
  usan el mismo espacio de códigos de estación municipal.
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que en las
  tareas 003-007 y por la misma razón: la tarea prohibía dejar algo
  programado o escribir sin acotar en el disco de la EC2.
- **Sin variables de entorno de credenciales**: ambos recursos de
  datos.madrid.es usados son públicos y no las necesitan.

## Relevante para tareas futuras

- Ambos recursos (tiempo real y catálogo de estaciones) son completamente
  públicos y no dependen de ningún registro pendiente: el día que se
  implemente un productor continuo real para esta fuente, no hay ningún
  bloqueo de credenciales que resolver antes.
- AEMET OpenData sigue siendo una fuente complementaria no explorada en
  esta tarea (pronósticos, avisos, series históricas más largas); si una
  tarea futura la necesitara, requerirá gestionar una API key gratuita vía
  variable de entorno, siguiendo el mismo patrón que `EMT_API_EMAIL`/
  `EMT_API_PASSWORD` de la tarea 003.
- Igual que en las tareas 003-007, este productor sigue sin estar
  conectado a ningún destino de almacenamiento definitivo (S3/Bronze); eso
  llegará en una tarea posterior, tras aplicar la infraestructura de la
  tarea 001.
- `TODO(kafka)` queda marcado en el módulo para cuando exista un broker
  Kafka desplegado, igual que en los productores anteriores.
- Esta es la tercera fuente (tras calidad del aire en la tarea 006) que usa
  el backend "bdca" del Servicio de Calidad del Aire del Ayuntamiento;
  cualquier tarea futura que añada una fuente similar de ese mismo backend
  puede reutilizar directamente el patrón `_latest_valid_hour`/`_measured_at`
  de `meteorologia_madrid.py`/`calidad_aire_madrid.py`.
