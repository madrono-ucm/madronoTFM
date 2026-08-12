# 004 — Captura de datos de BiciMAD (bicicleta compartida, muestra)

## Qué se implementó

Tercer productor de datos de la Fase 1 (Ingesta), siguiendo el mismo patrón
que las tareas 002/003, con el mismo alcance reducido que la tarea 003
(captura puntual de muestra, no productor continuo — la infraestructura AWS
de la tarea 001 sigue sin aplicarse):

- `ingesta/capturas/bicimad.py`: descarga el estado de las estaciones de
  BiciMAD (bicis y anclajes disponibles) desde el feed público **GBFS**
  (General Bikeshare Feed Specification) de la EMT Madrid, cruzando sus dos
  sub-feeds `station_information` (metadatos fijos: nombre, dirección,
  lat/lon, capacidad) y `station_status` (estado variable: bicis/anclajes
  disponibles, `last_reported`) por `station_id`, los normaliza a un esquema
  mínimo, y guarda una **muestra pequeña** (5 estaciones por defecto,
  configurable) en un fichero fijo — sin bucle, sin `--interval-seconds`, sin
  escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/bicimad_sample.json`: la muestra pequeña
  commiteada como fixture (5 estaciones).
- `ingesta/tests/test_bicimad.py` +
  `ingesta/tests/fixtures/bicimad_station_information_sample.json` +
  `ingesta/tests/fixtures/bicimad_station_status_sample.json`: tests con
  `unittest` (sin red) que verifican el cruce/normalización, incluido el
  caso de una estación presente en `station_information` pero sin entrada
  correspondiente en `station_status`, y que la muestra commiteada cumple el
  esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida,
  variables de entorno, esquema, y la nota sobre el acceso en vivo desde
  este entorno).

## Fuente elegida y por qué: feed GBFS público, sin autenticación

La propia tarea sugería comprobar primero si BiciMAD ofrece un feed estándar
GBFS antes de recurrir al portal opendata.emtmadrid.es (que sí requiere
registro). Se confirmó que **sí lo ofrece**: está catalogado como dataset
"Bicimad. GBFS" tanto en
[datos.madrid.es](https://datos.madrid.es/dataset/900021-0-bicimad-gbfs) como
en
[datos.emtmadrid.es](https://datos.emtmadrid.es/dataset/gbfs-general-bikeshare-feed-specification-de-bicimad),
con documento de descubrimiento en
`https://madrid.publicbikesystem.net/customer/gbfs/v2/gbfs.json`.

Se verificó en vivo desde este entorno que `station_information` y
`station_status` (y el resto de sub-feeds GBFS) responden con datos reales
**sin ninguna cabecera de autenticación ni API key** — a diferencia de la
API MobilityLabs usada en la tarea 003 (transporte público), que exige una
cuenta registrada y verificada por email. Por eso se descartó la alternativa
de usar la API MobilityLabs específica de BiciMAD
(`openapi.emtmadrid.es/v1/transport/bicimad/stations/<id>/`), que habría
tenido el mismo bloqueo de verificación manual que la tarea 003.

Consecuencia práctica: a diferencia de la tarea 003, **esta vez sí fue
posible completar una captura real en vivo**. El fixture commiteado
(`ingesta/capturas/samples/bicimad_sample.json`) son 5 estaciones reales de
BiciMAD (Metro Callao, Plaza Conde Suchil, Malasaña, Fuencarral, Colegio de
Arquitectos), descargadas ejecutando `python3 -m ingesta.capturas.bicimad`
tal cual contra el feed público durante esta sesión — no son datos de
ejemplo generados a mano. El sistema completo tenía 674 estaciones activas
en el momento de la captura.

## Esquema normalizado

Por estación: `schema_version`, `source` (`"bicimad_gbfs"`), `station_id`,
`name`, `address`, `measured_at` (UTC, de `station_status.last_reported`),
`ingested_at` (UTC, instante de la descarga), `bikes_available`,
`bikes_disabled`, `docks_available`, `docks_disabled`, `docks_total` (de
`station_information.capacity`), `status`, `is_renting`, `is_returning`,
`is_installed`, y `location` (`lat`/`lon` WGS84 estándar, no UTM — igual que
en la tarea 003). Detalle completo en `ingesta/README.md`.

## Decisiones de diseño (por qué)

- **Cruce de dos feeds por `station_id`** (`station_information` +
  `station_status`) en vez de usar solo uno: GBFS separa a propósito los
  metadatos fijos de una estación (que cambian rara vez) de su estado
  variable (que cambia constantemente), y el objetivo de la tarea pide
  ambos tipos de campo (ubicación + bicis/anclajes disponibles) en un único
  registro normalizado.
- **Estaciones sin estado sincronizado no se descartan**: si una estación
  aparece en `station_information` pero no (todavía) en `station_status`
  —posible por una desincronización momentánea entre los dos feeds, cada uno
  con su propio `ttl`—, se normaliza igualmente con los campos de estado a
  `null`, en vez de omitirla. Mismo criterio que en la tarea 002 con los
  sensores de tráfico en error: Bronze/la muestra deben reflejar la fuente
  tal cual, no solo el subconjunto "limpio".
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que en la tarea
  003 y por la misma razón: la tarea prohibía explícitamente dejar algo
  programado o escribir sin acotar en el disco de la EC2. El escritor de
  muestra escribe siempre en la misma ruta fija (sobrescribiendo), acotado a
  `BICIMAD_SAMPLE_SIZE` (5 por defecto) estaciones.
- **Sin variables de entorno de credenciales**: a diferencia de
  `trafico_madrid.py` y `transporte_publico_madrid.py`, este módulo no
  define ningún campo de autenticación en `CaptureConfig` porque el feed
  GBFS no lo necesita — se prefirió no añadir parámetros sin uso real.

## Relevante para tareas futuras

- El feed GBFS de BiciMAD es completamente público y no depende de ningún
  registro pendiente (a diferencia de la EMT MobilityLabs de la tarea 003):
  el día que se implemente un productor continuo real para esta fuente, no
  hay ningún bloqueo de credenciales que resolver antes.
- Igual que en la tarea 003, este productor sigue sin estar conectado a
  ningún destino de almacenamiento definitivo (S3/Bronze); cuando se aplique
  la infraestructura de la tarea 001 y se decida operar esta fuente de forma
  recurrente, habrá que decidir si reutiliza `BronzeWriter` (como tráfico) o
  un escritor de muestra/lote distinto, y añadir un modo de captura
  periódica si se decide operarlo así.
- `TODO(kafka)` queda marcado en el módulo para cuando exista un broker
  Kafka desplegado, igual que en los productores anteriores.
- El feed GBFS completo (674 estaciones a fecha de esta captura) también
  expone `geofencing_zones`, `system_pricing_plans`, `system_regions` y
  `vehicle_types`, no usados por esta tarea (fuera de su alcance: solo pedía
  estado de estaciones) pero disponibles si una tarea futura los necesitara.
