# ingesta

Productores de datos que capturan fuentes abiertas y las aterrizan en la capa
Bronze del lakehouse (Fase 1 del proyecto, ver `documents/Memoria_TFM FV.docx`,
apartado 6.1). Cada fuente (tráfico, transporte público, bicicleta
compartida, calidad del aire, ruido, meteorología...) es un módulo bajo
`ingesta/capturas/` que sigue el mismo patrón: descarga -> normaliza a un
esquema mínimo y consistente -> escribe un lote en Bronze vía
`ingesta.capturas.bronze.BronzeWriter`.

Todavía no hay un broker Kafka desplegado (ver tarea 001), así que la mayoría
de estos productores están pensados para ejecutarse periódicamente (cron,
systemd timer, o su propio modo `--interval-seconds`) y escriben directamente
a disco. El punto donde se conectaría un productor Kafka está marcado con
`TODO(kafka)` en cada módulo. Las excepciones son `transporte_publico_madrid.py`
(tarea 003), `bicimad.py` (tarea 004), `aparcamientos_madrid.py` (tarea 005),
`calidad_aire_madrid.py` (tarea 006), `ruido_madrid.py` (tarea 007) y
`meteorologia_madrid.py` (tarea 008) y `afluencia_lugares_madrid.py` (tarea
012), que a propósito solo hacen capturas puntuales de muestra — ver sus
secciones más abajo.

`callejero_madrid.py` (tarea 009) es un caso distinto de los anteriores: no
es un dato que cambie con el tiempo (tráfico, calidad del aire...), sino un
dato de **referencia** (el callejero y grafo viario de Madrid) que apenas
varía. Por eso es, a propósito, una **carga batch puntual**, no solo una
"muestra reducida por falta de infraestructura" — nunca necesitará
programarse periódicamente, ni siquiera cuando exista infraestructura real.
`barrios_distritos_madrid.py` (tarea 010) y `poi_madrid.py` (tarea 011) son
del mismo tipo: los límites administrativos de barrios y distritos, y los
puntos de interés turístico de Madrid, también son datos de referencia. Ver
sus secciones más abajo.

`afluencia_lugares_madrid.py` (tarea 012) es también un caso especial, pero
por un motivo distinto: no es un dato de referencia ni le falta
infraestructura, sino que su fuente (una librería que hace scraping de un
endpoint no documentado de Google) es una **zona gris** admisible solo en el
marco académico de este TFM (ver `documents/Memoria_TFM FV.docx`, apartado
6.8, y la sección propia de este módulo más abajo) — nunca debería escalarse
a un productor continuo tal cual, ni siquiera cuando exista infraestructura
real.

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r ingesta/requirements.txt
```

## `capturas/trafico_madrid.py` — Intensidad de tráfico de Madrid

Descarga el feed en tiempo real de intensidad de tráfico del Ayuntamiento de
Madrid (servicio Informo, dataset "Tráfico. Intensidad y velocidad" de
[datos.madrid.es](https://datos.madrid.es)):
<https://informo.madrid.es/informo/tmadrid/pm.xml>. Es un XML público, sin
autenticación, con ~4.500 puntos de medida (sensores) y su intensidad,
ocupación, carga y nivel de servicio actuales.

### Ejecutar

```bash
# Una captura puntual (pensado para invocar desde cron/systemd timer):
python3 -m ingesta.capturas.trafico_madrid

# Captura continua cada 5 minutos, sin depender de un scheduler externo:
python3 -m ingesta.capturas.trafico_madrid --interval-seconds 300
```

Cada ejecución puntual escribe **un** fichero JSON con la lista de registros
normalizados de esa captura en:

```
$BRONZE_BASE_PATH/trafico/fecha=YYYY-MM-DD/hora=HH/<timestamp>_<sufijo>.json
```

### Variables de entorno

| Variable                     | Por defecto                                       | Descripción                                                       |
| ----------------------------- | -------------------------------------------------- | ------------------------------------------------------------------ |
| `BRONZE_BASE_PATH`            | `./bronze`                                          | Ruta base de la capa Bronze. Local por ahora; el día que exista el bucket S3 de la tarea 001, apuntar aquí a un punto de montaje S3 sin tocar código. |
| `MADRID_TRAFFIC_SOURCE_URL`   | `https://informo.madrid.es/informo/tmadrid/pm.xml`  | URL del feed de tráfico.                                            |
| `HTTP_TIMEOUT_SECONDS`        | `15`                                                 | Timeout por request HTTP.                                          |
| `HTTP_MAX_RETRIES`            | `3`                                                  | Reintentos ante fallo de red (backoff lineal simple).              |
| `HTTP_RETRY_BACKOFF_SECONDS`  | `2`                                                  | Base del backoff entre reintentos (segundos * intento).            |
| `LOG_LEVEL`                   | `INFO`                                               | Nivel de logging (también configurable con `--log-level`).         |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_trafico_intensidad",
  "point_id": "9841",
  "measured_at": "2026-08-11T23:45:04+00:00",
  "ingested_at": "2026-08-11T23:45:07.123456+00:00",
  "description": "Valle de Mena S-E - Acc.Ramon Castroviejo-Gta.Isaac Rabín",
  "access_code": "0301005",
  "subarea": "0328",
  "intensity_vph": 20,
  "occupancy_pct": 0,
  "load_pct": 0,
  "service_level": 0,
  "saturation_intensity_vph": 3100,
  "has_error": false,
  "error_code": "N",
  "location": {"x": 438339.375874991, "y": 4480454.96970565, "srid": "EPSG:25830"}
}
```

- `measured_at`: timestamp global del feed (hora de Madrid convertida a UTC).
  Es el mismo para todos los registros de una misma captura, tal como lo
  publica la fuente (un único `fecha_hora` para todo el XML).
- `ingested_at`: instante en que este productor descargó el feed (UTC).
- `location.x`/`location.y`: coordenadas tal como vienen en la fuente
  (UTM ETRS89 huso 30N, EPSG:25830, con coma decimal en origen — ya
  convertidas a `float` con punto). No se reproyecta a lat/lon en esta tarea
  para no añadir una dependencia de geoprocesado (p.ej. `pyproj`) sin
  necesidad; queda como posible mejora futura si una tarea de Silver/Gold la
  necesita en WGS84.
- Campos ausentes o vacíos en la fuente (p.ej. sensores con `error=S`) se
  normalizan a `null`, no se descartan — Bronze debe conservar el registro
  tal cual llega, errores incluidos.

## `capturas/transporte_publico_madrid.py` — Llegadas de EMT Madrid a una parada (muestra puntual)

Descarga los próximos tiempos de llegada de autobús en una parada concreta
usando la API REST "MobilityLabs" de la EMT Madrid (Empresa Municipal de
Transportes), catalogada en [datos.emtmadrid.es](https://datos.emtmadrid.es);
documentación y registro en
[mobilitylabs.emtmadrid.es/es/portal/opendata](https://mobilitylabs.emtmadrid.es/es/portal/opendata).

A diferencia de `trafico_madrid.py`, **este productor es solo una captura
puntual** que genera una muestra pequeña versionada como fixture — no admite
bucle ni scheduling propio (ver "Alcance reducido" más abajo).

### Autenticación (API key gratuita)

La API no usa una API key simple, sino email + contraseña de una cuenta
registrada gratis en <https://mobilitylabs.emtmadrid.es> ("Regístrate"). Tras
el registro, la EMT envía un correo de confirmación que hay que validar antes
de que la cuenta pueda autenticarse. Una vez verificada, el login es:

```
GET https://openapi.emtmadrid.es/v1/mobilitylabs/user/login/
Headers: email: <tu email>, password: <tu contraseña>
```

que devuelve un `accessToken` (en `data[0].accessToken`) a reenviar en la
cabecera `accessToken` de la llamada de llegadas
(`POST /v2/transport/busemtmad/stops/{stop_id}/arrives/`). Las credenciales
se leen de `EMT_API_EMAIL` / `EMT_API_PASSWORD`, nunca hardcodeadas.

### Alcance reducido respecto a `trafico_madrid.py`

Todavía no se ha aplicado la infraestructura AWS (tarea 001), así que no hay
S3 ni base de datos donde aterrizar datos en volumen. Este productor, a
propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño (como mucho `EMT_SAMPLE_SIZE`, 5 por
  defecto) en una ruta fija, pensado para commitearse como fixture, no para
  acumularse en disco.

### Ejecutar

```bash
export EMT_API_EMAIL="tu-email@ejemplo.com"
export EMT_API_PASSWORD="tu-contraseña"
python3 -m ingesta.capturas.transporte_publico_madrid --stop-id 71
```

Escribe la muestra en `ingesta/capturas/samples/transporte_publico_madrid_sample.json`
(configurable con `--out`).

### Nota sobre el acceso desde este entorno (tarea 003)

Se verificó en vivo que `https://openapi.emtmadrid.es` es alcanzable desde
este entorno y que el endpoint de login funciona (probado sin credenciales:
`{"code": "99", ...}`; con un email/contraseña de prueba sin registrar:
`{"code": "91", "description": "Error: Email is not verified..."}`). La API
es accesible, pero requiere una cuenta con email real verificado por
correo — un paso manual no automatizable de forma autónoma en este pipeline
(no hay bandeja de correo ni humano disponible durante la sesión para
completarlo). Por eso, el fixture commiteado en
`ingesta/capturas/samples/transporte_publico_madrid_sample.json` se generó a
mano con datos de ejemplo realistas que siguen exactamente el esquema que
produce `normalize_record` (mismos campos, mismo formato, IDs de
parada/línea/bus ilustrativos), en vez de descargarse en vivo. El código de
captura queda completo y listo para ejecutarse tal cual el día que alguien
complete el registro y verificación de una cuenta EMT real.

### Variables de entorno

| Variable                | Por defecto                    | Descripción                                                  |
| ------------------------ | -------------------------------- | -------------------------------------------------------------- |
| `EMT_API_EMAIL`          | *(ninguno, requerido)*           | Email de una cuenta MobilityLabs registrada y verificada.      |
| `EMT_API_PASSWORD`       | *(ninguno, requerido)*           | Contraseña de esa cuenta.                                       |
| `EMT_API_BASE_URL`       | `https://openapi.emtmadrid.es`   | URL base de la API.                                              |
| `EMT_STOP_ID`            | `71`                              | ID de parada EMT a consultar (también con `--stop-id`).         |
| `EMT_SAMPLE_SIZE`        | `5`                               | Nº máximo de registros que se guardan en la muestra.             |
| `HTTP_TIMEOUT_SECONDS`   | `15`                              | Timeout por request HTTP.                                        |
| `HTTP_MAX_RETRIES`       | `3`                               | Reintentos ante fallo de red (backoff lineal simple).            |
| `HTTP_RETRY_BACKOFF_SECONDS` | `2`                           | Base del backoff entre reintentos (segundos * intento).          |
| `LOG_LEVEL`              | `INFO`                            | Nivel de logging (también configurable con `--log-level`).       |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_emt_llegadas",
  "stop_id": "71",
  "line": "27",
  "bus_id": 1234,
  "destination": "PLAZA CASTILLA",
  "ingested_at": "2026-08-12T09:15:30+00:00",
  "estimate_arrive_sec": 180,
  "distance_bus_m": 950,
  "is_head": false,
  "deviation_sec": 0,
  "position_type_bus": "1",
  "location": {"lon": -3.700123, "lat": 40.420456, "srid": "EPSG:4326"}
}
```

- `ingested_at`: instante en que este productor consultó la API (UTC).
- `estimate_arrive_sec`: segundos estimados hasta la llegada del autobús a la
  parada (tal como lo da la fuente, sin redondear a minutos).
- `location.lon`/`location.lat`: coordenadas del autobús tal como las da la
  fuente (GeoJSON `Point`, WGS84 — a diferencia del feed de tráfico, aquí la
  fuente ya usa lon/lat estándar, no UTM).
- Campos ausentes en la fuente (p.ej. una llegada sin `line`/`bus`/coordenadas)
  se normalizan a `null`, no se descartan.

## `capturas/bicimad.py` — Estado de estaciones de BiciMAD (muestra puntual)

Descarga el estado de las estaciones de BiciMAD (bicis y anclajes
disponibles) desde el feed público **GBFS** (General Bikeshare Feed
Specification) que publica la EMT Madrid — catalogado como dataset "Bicimad.
GBFS" tanto en [datos.madrid.es](https://datos.madrid.es/dataset/900021-0-bicimad-gbfs)
como en [datos.emtmadrid.es](https://datos.emtmadrid.es/dataset/gbfs-general-bikeshare-feed-specification-de-bicimad).
Documento de descubrimiento GBFS:
<https://madrid.publicbikesystem.net/customer/gbfs/v2/gbfs.json>.

Igual que `transporte_publico_madrid.py`, **este productor es solo una
captura puntual** que genera una muestra pequeña versionada como fixture — no
admite bucle ni scheduling propio (ver "Alcance reducido" más abajo).

### Sin autenticación: feed GBFS público

A diferencia de `transporte_publico_madrid.py` (API MobilityLabs, que exige
una cuenta registrada y verificada por email), **el feed GBFS de BiciMAD no
requiere ninguna API key ni registro**. Se ha verificado en vivo desde este
entorno que `station_information` y `station_status` responden sin ninguna
cabecera de autenticación. GBFS es el estándar de facto para sistemas de
bicicleta/patinete compartidos, y BiciMAD lo publica completo (674
estaciones a fecha de esta captura), así que se prefirió sobre la
alternativa de usar la API MobilityLabs de BiciMAD
(`openapi.emtmadrid.es/v1/transport/bicimad/stations/`), que sí requeriría
las mismas credenciales que bloquearon la tarea 003.

Este productor combina dos feeds GBFS por `station_id`:

- `station_information`: metadatos fijos de cada estación (nombre,
  dirección, lat/lon, capacidad total).
- `station_status`: estado variable (bicis y anclajes disponibles ahora
  mismo, `last_reported`).

### Alcance reducido respecto a `trafico_madrid.py`

Igual que en la tarea 003, todavía no se ha aplicado la infraestructura AWS
(tarea 001), así que este productor, a propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño (como mucho `BICIMAD_SAMPLE_SIZE`, 5 por
  defecto, de las ~670 estaciones de la red completa) en una ruta fija,
  pensado para commitearse como fixture, no para acumularse en disco.

### Ejecutar

```bash
python3 -m ingesta.capturas.bicimad
```

Escribe la muestra en `ingesta/capturas/samples/bicimad_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                          | Por defecto                                                                         | Descripción                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `BICIMAD_STATION_INFORMATION_URL`  | `https://madrid.publicbikesystem.net/customer/gbfs/v2/es/station_information`        | URL del feed GBFS de metadatos de estaciones.           |
| `BICIMAD_STATION_STATUS_URL`       | `https://madrid.publicbikesystem.net/customer/gbfs/v2/es/station_status`             | URL del feed GBFS de estado de estaciones.              |
| `BICIMAD_SAMPLE_SIZE`              | `5`                                                                                    | Nº máximo de estaciones que se guardan en la muestra.   |
| `HTTP_TIMEOUT_SECONDS`             | `15`                                                                                   | Timeout por request HTTP.                               |
| `HTTP_MAX_RETRIES`                 | `3`                                                                                    | Reintentos ante fallo de red (backoff lineal simple).   |
| `HTTP_RETRY_BACKOFF_SECONDS`       | `2`                                                                                    | Base del backoff entre reintentos (segundos * intento). |
| `LOG_LEVEL`                        | `INFO`                                                                                 | Nivel de logging (también configurable con `--log-level`). |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "bicimad_gbfs",
  "station_id": "1406",
  "name": "2 - Metro Callao",
  "address": "Calle Miguel Moya nº 1",
  "measured_at": "2026-08-12T01:13:00+00:00",
  "ingested_at": "2026-08-12T01:13:55.697210+00:00",
  "bikes_available": 2,
  "bikes_disabled": 2,
  "docks_available": 23,
  "docks_disabled": 0,
  "docks_total": 47,
  "status": "IN_SERVICE",
  "is_renting": true,
  "is_returning": true,
  "is_installed": true,
  "location": {"lat": 40.4204, "lon": -3.70569, "srid": "EPSG:4326"}
}
```

- `measured_at`: `last_reported` del feed `station_status` (por estación,
  UTC). Puede ser `null` si una estación de `station_information` no tiene
  entrada correspondiente en `station_status` (desincronización entre
  feeds); en ese caso todos los campos de estado se normalizan a `null` en
  vez de descartar la estación — los metadatos fijos (`name`, `docks_total`,
  `location`...) siempre están presentes.
- `ingested_at`: instante en que este productor consultó ambos feeds (UTC).
- `docks_total`: capacidad total de la estación (`capacity` en
  `station_information`); `docks_available`/`docks_disabled` son el desglose
  actual de `station_status`.
- `location.lat`/`location.lon`: coordenadas tal como las da la fuente
  (WGS84 estándar, no UTM).

### Nota sobre el acceso desde este entorno (tarea 004)

A diferencia de la tarea 003, aquí sí fue posible completar una captura real
en vivo: el fixture commiteado en
`ingesta/capturas/samples/bicimad_sample.json` son 5 estaciones reales,
descargadas ejecutando el script tal cual contra el feed público durante
esta sesión — no son datos de ejemplo generados a mano.

## `capturas/aparcamientos_madrid.py` — Ocupación de aparcamientos públicos de Madrid (muestra puntual)

Descarga la ocupación en tiempo real (plazas libres, y plazas totales por
aparcamiento) del dataset "Aparcamientos públicos (rotacionales). Datos de
ocupación en tiempo real" (id `50027-0-aparcamientosocupacionyservicios`) de
[datos.madrid.es](https://datos.madrid.es/dataset/50027-0-aparcamientosocupacionyservicios):
agrega los aparcamientos rotacionales (municipales y privados) que comparten
voluntariamente su ocupación con el Ayuntamiento — el mismo sistema que
alimenta la app "Parking Madrid".

Igual que `transporte_publico_madrid.py` y `bicimad.py`, **este productor es
solo una captura puntual** que genera una muestra pequeña versionada como
fixture — no admite bucle ni scheduling propio (ver "Alcance reducido" más
abajo).

### Fuente elegida y por qué: servicio SOAP `infoParking`, sin autenticación

A diferencia de los feeds HTTP simples usados en tareas anteriores (XML de
Informo en tráfico, JSON GBFS en BiciMAD), este dataset **no publica un
XML/JSON descargable directamente**: su único recurso de datos es un
servicio **SOAP** (WSDL "infoParking"), descargable desde:

<https://datos.madrid.es/dataset/50027-0-aparcamientosocupacionyservicios/resource/50027-1-aparcamientosocupacionyservicios/download/50027-1-aparcamientosocupacionyservicios.wsdl>

que apunta al endpoint real `https://servayto.madrid.es/MTPAR_WSINFO/InfoParking`.
Se ha verificado en vivo desde este entorno que este endpoint SOAP **no
requiere ninguna autenticación ni API key**. Se descartaron dos alternativas
encontradas en la investigación:

- **"Aparcamientos EMT"** (datos.emtmadrid.es): subconjunto más pequeño
  (aparcamientos disuasorios) sin un feed de ocupación en tiempo real tan
  directo como este.
- **"Aparcamientos públicos municipales (rotacionales). Histórico de
  ocupación"** (dataset 300346): es un agregado mensual/histórico, no
  ocupación en tiempo real.

Este productor usa dos operaciones SOAP:

- `GetListParking`: listado completo de aparcamientos (75 en el momento de
  esta captura), con nombre, dirección, coordenadas y, para los que
  comparten su ocupación (es voluntario — no todos la incluyen), plazas
  libres (`lstOccupation`).
- `GetDetailParking` (una llamada por aparcamiento de la muestra): plazas
  totales, en `lstFeatures` como la característica de tipo "Tipo plaza"
  llamada "Total".

### Alcance reducido respecto a `trafico_madrid.py`

Igual que en las tareas 003/004, todavía no se ha aplicado la infraestructura
AWS (tarea 001), así que este productor, a propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño (como mucho `MADRID_PARKING_SAMPLE_SIZE`,
  5 por defecto, de los aparcamientos con ocupación en tiempo real
  disponible) en una ruta fija, pensado para commitearse como fixture, no
  para acumularse en disco.

### Ejecutar

```bash
python3 -m ingesta.capturas.aparcamientos_madrid
```

Escribe la muestra en `ingesta/capturas/samples/aparcamientos_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                       | Por defecto                                          | Descripción                                                     |
| -------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------ |
| `MADRID_PARKING_ENDPOINT_URL`   | `https://servayto.madrid.es/MTPAR_WSINFO/InfoParking`  | URL del endpoint SOAP `infoParking`.                              |
| `MADRID_PARKING_SAMPLE_SIZE`    | `5`                                                      | Nº máximo de aparcamientos que se guardan en la muestra.           |
| `HTTP_TIMEOUT_SECONDS`          | `15`                                                     | Timeout por request HTTP.                                          |
| `HTTP_MAX_RETRIES`              | `3`                                                       | Reintentos ante fallo de red (backoff lineal simple).              |
| `HTTP_RETRY_BACKOFF_SECONDS`    | `2`                                                       | Base del backoff entre reintentos (segundos * intento).            |
| `LOG_LEVEL`                     | `INFO`                                                    | Nivel de logging (también configurable con `--log-level`).         |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_aparcamientos_rotacionales",
  "parking_id": "5",
  "name": "Nuestra Señora del Recuerdo",
  "address": "Calle de la Hiedra",
  "measured_at": "2026-08-12T01:19:25+00:00",
  "ingested_at": "2026-08-12T01:21:22.368415+00:00",
  "free_spaces": 431,
  "total_spaces": 832,
  "location": {"lat": 40.472181, "lon": -3.67916, "srid": "EPSG:4326"}
}
```

- `measured_at`: momento de la última actualización de ocupación que reporta
  la fuente (`lstOccupation.moment`, convertido de hora de Madrid a UTC).
  `null` si el aparcamiento no comparte ocupación en tiempo real.
- `ingested_at`: instante en que este productor consultó la fuente (UTC).
- `free_spaces`: plazas libres ahora mismo (`GetListParking`); `null` si el
  aparcamiento no comparte ocupación en tiempo real (es voluntario).
- `total_spaces`: plazas totales (`GetDetailParking`, característica "Total");
  `null` si no se pudo obtener.
- `location.lat`/`location.lon`: coordenadas tal como las da la fuente
  (WGS84 estándar, no UTM).

### Nota sobre el acceso desde este entorno (tarea 005)

Igual que en la tarea 004, fue posible completar una captura real en vivo: el
fixture commiteado en
`ingesta/capturas/samples/aparcamientos_madrid_sample.json` son 5
aparcamientos reales, descargados ejecutando el script tal cual contra el
servicio SOAP público durante esta sesión (de los 75 aparcamientos del
listado completo, 24 compartían ocupación en tiempo real en el momento de la
captura) — no son datos de ejemplo generados a mano.

## `capturas/calidad_aire_madrid.py` — Calidad del aire de Madrid (muestra puntual)

Descarga las lecturas horarias en tiempo real de la red de estaciones de
control de contaminación del Ayuntamiento de Madrid, dataset "Calidad del
aire. Datos en tiempo real" (id `212531-0-calidad-aire-tiempo-real`) de
[datos.madrid.es](https://datos.madrid.es/egob/catalogo/212531-0-calidad-aire-tiempo-real):
actualizadas cada 20 minutos (minutos 15/35/55) para las 24 estaciones fijas
de la red.

Igual que `transporte_publico_madrid.py`, `bicimad.py` y
`aparcamientos_madrid.py`, **este productor es solo una captura puntual**
que genera una muestra pequeña versionada como fixture — no admite bucle ni
scheduling propio (ver "Alcance reducido" más abajo).

### Formato real encontrado

El dataset ofrece TXT, CSV, JSON y XML con el mismo contenido; se eligió
**JSON** por ser el más simple de parsear sin dependencias extra (a
diferencia del XML de tráfico de la tarea 002). Se confirmó el formato
descargando el recurso en vivo y contrastándolo con el PDF "Intérprete de
ficheros de calidad del aire" que publica el propio dataset: no es una
lista plana de lecturas, sino **un registro por combinación
estación+magnitud+día**, con las 24 lecturas horarias de ese día ya
embebidas en columnas `H01`..`H24` (cada una con su código de validación
`V01`..`V24`: `"V"` = válido, `"N"` = no válido/sin dato). El campo
`PUNTO_MUESTREO` (p.ej. `"28079011_12_8"`) codifica estación (`28079011`) +
magnitud (`12`) + técnica de muestreo (`8`); el campo `MAGNITUD` da el
código de magnitud sin ceros a la izquierda (`"1"` en vez de `"01"`), que
esta captura normaliza con `zfill(2)` contra la tabla de magnitudes del
Anexo II del PDF (códigos y unidades de SO2, NO, NO2, PM2.5, PM10, NOx, O3,
BTX...).

El JSON de tiempo real no incluye nombre, dirección ni coordenadas de la
estación (solo su código), así que este productor hace una segunda
descarga al dataset "Calidad del aire. Estaciones de control" (id
`212629-0-estaciones-control-aire`), un CSV con esos metadatos por
estación — mismo patrón de combinar dos fuentes que `aparcamientos_madrid.py`
(`GetListParking` + `GetDetailParking`) o `bicimad.py`
(`station_information` + `station_status`).

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

### Alcance reducido respecto a `trafico_madrid.py`

Igual que en las tareas 003/004/005, todavía no se ha aplicado la
infraestructura AWS (tarea 001), así que este productor, a propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño (como mucho `MADRID_AIR_QUALITY_SAMPLE_SIZE`,
  5 por defecto, de las 123 lecturas estación+magnitud que devolvió la
  fuente en el momento de esta captura) en una ruta fija, pensado para
  commitearse como fixture, no para acumularse en disco.

### Ejecutar

```bash
python3 -m ingesta.capturas.calidad_aire_madrid
```

Escribe la muestra en `ingesta/capturas/samples/calidad_aire_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                          | Por defecto                                                                                                        | Descripción                                                     |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `MADRID_AIR_QUALITY_REALTIME_URL` | URL del recurso JSON de tiempo real (ver módulo)                                                                       | URL del JSON de lecturas horarias en tiempo real.                  |
| `MADRID_AIR_QUALITY_STATIONS_URL` | URL del recurso CSV de estaciones (ver módulo)                                                                         | URL del CSV del catálogo de estaciones de control.                 |
| `MADRID_AIR_QUALITY_SAMPLE_SIZE`  | `5`                                                                                                                      | Nº máximo de lecturas que se guardan en la muestra.                |
| `HTTP_TIMEOUT_SECONDS`            | `15`                                                                                                                     | Timeout por request HTTP.                                          |
| `HTTP_MAX_RETRIES`                | `3`                                                                                                                       | Reintentos ante fallo de red (backoff lineal simple).              |
| `HTTP_RETRY_BACKOFF_SECONDS`      | `2`                                                                                                                       | Base del backoff entre reintentos (segundos * intento).            |
| `LOG_LEVEL`                       | `INFO`                                                                                                                    | Nivel de logging (también configurable con `--log-level`).         |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_calidad_aire",
  "station_id": "28079011",
  "station_name": "Ramón y Cajal",
  "station_address": "Avda. Ramón y Cajal  esq. C/ Príncipe de Vergara",
  "magnitude_code": "12",
  "magnitude_abbr": "NOx",
  "magnitude_name": "Óxidos de Nitrógeno",
  "unit": "µg/m³",
  "value": 37.0,
  "measured_at": "2026-08-12T00:00:00+00:00",
  "ingested_at": "2026-08-12T01:30:08.436733+00:00",
  "location": {"lat": 40.4514734, "lon": -3.6773491, "srid": "EPSG:4326"}
}
```

- Cada registro es la lectura horaria **válida más reciente del día** para
  una combinación estación+magnitud (la fuente da las 24 horas del día en
  un único registro; este productor se queda con la última marcada como
  válida, `V`, análogo a mostrar el estado "actual" en las demás capturas
  puntuales de este proyecto).
- `measured_at`: hora de esa lectura (de `ANO`/`MES`/`DIA` + la hora `Hxx`
  elegida, hora de Madrid convertida a UTC). `ingested_at`: instante en que
  este productor consultó ambas fuentes (UTC).
- `station_name`/`station_address`/`location`: `null` si el código de
  estación de la lectura no aparece en el catálogo de estaciones descargado
  (no debería ocurrir en condiciones normales, pero se normaliza así en vez
  de descartar la lectura, mismo criterio que en el resto de capturas).
- `location.lat`/`location.lon`: coordenadas del catálogo de estaciones
  (WGS84 estándar, no UTM).
- Lecturas sin ninguna hora válida ese día (las 24 marcadas `N`) se
  descartan de la muestra (`normalize_record` devuelve `None`): no aportan
  ningún valor de calidad del aire que capturar.

### Nota sobre el acceso desde este entorno (tarea 006)

Igual que en las tareas 004/005, fue posible completar una captura real en
vivo: el fixture commiteado en
`ingesta/capturas/samples/calidad_aire_madrid_sample.json` son 5 lecturas
reales (estaciones Ramón y Cajal y Arturo Soria; magnitudes NOx, NO, NO2 y
O3), descargadas ejecutando el script tal cual contra ambos recursos
públicos durante esta sesión — no son datos de ejemplo generados a mano.

## `capturas/ruido_madrid.py` — Contaminación acústica (ruido) de Madrid (muestra puntual)

Descarga los valores diarios de contaminación acústica de la Red Fija del
Sistema Integral de Vigilancia de la Contaminación Acústica (SIVCA) del
Ayuntamiento de Madrid, dataset "Contaminación acústica. Datos diarios" (id
`215885-0-contaminacion-ruido`) de
[datos.madrid.es](https://datos.madrid.es/dataset/215885-0-contaminacion-ruido):
LAeq y percentiles L1/L10/L50/L90/L99 por estación y por periodo horario
(diurno, vespertino, nocturno, total), actualizados a diario (excepto fines
de semana y festivos) para las 31 estaciones fijas de la red.

Igual que `transporte_publico_madrid.py`, `bicimad.py`,
`aparcamientos_madrid.py` y `calidad_aire_madrid.py`, **este productor es
solo una captura puntual** que genera una muestra pequeña versionada como
fixture — no admite bucle ni scheduling propio (ver "Alcance reducido" más
abajo).

### Formato real encontrado y por qué esta fuente (no una de tiempo real)

A diferencia de calidad del aire (tarea 006), **no existe en datos.madrid.es
un dataset de ruido con granularidad horaria/tiempo real**: la Red Fija del
SIVCA solo publica un agregado **diario** por estación+periodo. El resto de
datasets de ruido del portal (histórico mensual, mapas estratégicos de
ruido) son agregados a un plazo aún mayor, peor ajuste para una muestra
"actual". Se eligió por tanto el dataset diario por ser el más granular y
más actualizado disponible para esta red — sigue encajando con lo que pedía
la tarea ("datos.madrid.es publica niveles sonoros por estación").

El recurso descargable es un único CSV con el **histórico completo desde
2014** (~540.000 filas, ~24 MB a fecha de esta captura), en formato
ISO-8859-1 (Latin-1, a diferencia del UTF-8 de calidad del aire) y con coma
decimal (p.ej. `"62,9"`). No hay un recurso separado por día, así que
`parse_latest_day_entries` recorre el CSV completo pero solo conserva en
memoria las filas del último día presente en el fichero (que está ordenado
cronológicamente ascendente), en vez de acumular las ~540.000 filas de
histórico.

El CSV diario **no incluye nombre, dirección ni coordenadas de la
estación** (solo su código numérico plano, p.ej. `"1"`), así que este
productor hace una segunda descarga al dataset "Estaciones de medición de
ruido de la Red Fija del SIVCA" (id `211346-0-estaciones-acusticas`), un CSV
con esos metadatos por estación (código `RF-01`, `RF-02`...) — mismo patrón
de combinar dos fuentes que `calidad_aire_madrid.py`,
`aparcamientos_madrid.py` y `bicimad.py`. Ese catálogo publica latitud y
longitud en un formato peculiar (p.ej. `"-3.691.877"` en vez de
`-3.691877`): puntos de más, resultado de exportar un decimal con separador
de miles; `_parse_grouped_decimal` lo corrige tomando el primer fragmento
como parte entera y concatenando el resto como parte decimal.

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

### Alcance reducido respecto a `trafico_madrid.py`

Igual que en las tareas 003/004/005/006, todavía no se ha aplicado la
infraestructura AWS (tarea 001), así que este productor, a propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño en una ruta fija, pensado para
  commitearse como fixture, no para acumularse en disco. A diferencia de las
  tareas 003-006 (donde `..._SAMPLE_SIZE` cuenta *registros*), aquí
  `MADRID_NOISE_SAMPLE_STATIONS` cuenta **estaciones** (5 por defecto): cada
  estación aporta hasta 4 registros (uno por periodo D/E/N/T) del último día
  disponible, así que la muestra sigue siendo pequeña (20 registros con el
  valor por defecto) pero cubre varias estaciones completas, en línea con
  "unas pocas estaciones" del objetivo de la tarea.

### Ejecutar

```bash
python3 -m ingesta.capturas.ruido_madrid
```

Escribe la muestra en `ingesta/capturas/samples/ruido_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                       | Por defecto                                     | Descripción                                                |
| -------------------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| `MADRID_NOISE_DAILY_URL`       | URL del CSV histórico diario (ver módulo)         | URL del CSV de contaminación acústica diaria.               |
| `MADRID_NOISE_STATIONS_URL`    | URL del CSV de estaciones (ver módulo)            | URL del CSV del catálogo de estaciones de la Red Fija.       |
| `MADRID_NOISE_SAMPLE_STATIONS` | `5`                                                 | Nº máximo de estaciones (no registros) incluidas en la muestra. |
| `HTTP_TIMEOUT_SECONDS`         | `15`                                                | Timeout por request HTTP.                                    |
| `HTTP_MAX_RETRIES`             | `3`                                                 | Reintentos ante fallo de red (backoff lineal simple).        |
| `HTTP_RETRY_BACKOFF_SECONDS`   | `2`                                                 | Base del backoff entre reintentos (segundos * intento).      |
| `LOG_LEVEL`                    | `INFO`                                              | Nivel de logging (también configurable con `--log-level`).   |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_ruido_diario",
  "station_id": "RF-01",
  "station_name": "Paseo de Recoletos",
  "station_address": "Frente al n23 del Paseo de Recoletos",
  "district": "Centro",
  "neighbourhood": "Justicia",
  "period": "D",
  "period_name": "diurno",
  "measured_date": "2026-08-10",
  "ingested_at": "2026-08-12T01:40:10.464669+00:00",
  "laeq_db": 62.9,
  "l1_db": 69.7,
  "l10_db": 66.0,
  "l50_db": 60.4,
  "l90_db": 54.6,
  "l99_db": 52.2,
  "location": {"lat": 40.422599, "lon": -3.691877, "srid": "EPSG:4326", "altitude_m": 648}
}
```

- Cada registro es un agregado **diario** de una estación para un periodo
  horario concreto (`D` diurno, `E` vespertino, `N` nocturno, `T` total).
  Por eso usa `measured_date` (solo fecha) en vez de `measured_at` (instante
  con hora) como el resto de capturas: la fuente no publica una hora
  concreta, solo un día — este campo es honesto con esa granularidad real.
  `ingested_at` es el instante en que este productor consultó ambas fuentes
  (UTC).
- `laeq_db`/`l1_db`/`l10_db`/`l50_db`/`l90_db`/`l99_db`: nivel continuo
  equivalente y percentiles de presión sonora (dB), tal como define el PDF
  "Contaminación acústica. Datos diarios. Contenido y estructura del
  fichero" que publica el propio dataset.
- `station_id`: código normalizado del catálogo (`RF-01`..`RF-86`),
  construido con `zfill(2)` a partir del código numérico plano de la fuente
  (`"1"` -> `"RF-01"`).
- `station_name`/`station_address`/`district`/`neighbourhood`/`location`:
  `null` si el código de estación de la lectura no aparece en el catálogo de
  estaciones descargado (no debería ocurrir en condiciones normales, pero se
  normaliza así en vez de descartar la lectura, mismo criterio que en el
  resto de capturas).
- `location.lat`/`location.lon`: coordenadas del catálogo de estaciones ya
  en WGS84 decimal (tras corregir el formato de puntos de más de la fuente,
  ver más arriba), no UTM.

### Nota sobre el acceso desde este entorno (tarea 007)

Igual que en las tareas 004/005/006, fue posible completar una captura real
en vivo: el fixture commiteado en
`ingesta/capturas/samples/ruido_madrid_sample.json` son 20 lecturas reales
(estaciones RF-01 a RF-05, con sus 4 periodos cada una) del último día
disponible en el momento de la captura, descargadas ejecutando el script tal
cual contra ambos recursos públicos durante esta sesión — no son datos de
ejemplo generados a mano.

## `capturas/meteorologia_madrid.py` — Datos meteorológicos de Madrid (muestra puntual)

Descarga las lecturas horarias en tiempo real de la red de estaciones
meteorológicas del Ayuntamiento de Madrid, dataset "Datos meteorológicos.
Datos en tiempo real" (id `300392-0-meteorologia-tiempo-real`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300392-0-meteorologia-tiempo-real):
temperatura, humedad, viento, presión, radiación (solar y ultravioleta) y
precipitación, actualizadas cada 20 minutos (minutos 15/35/55) para ~25
estaciones fijas de la red.

Igual que `transporte_publico_madrid.py`, `bicimad.py`,
`aparcamientos_madrid.py`, `calidad_aire_madrid.py` y `ruido_madrid.py`,
**este productor es solo una captura puntual** que genera una muestra
pequeña versionada como fixture — no admite bucle ni scheduling propio (ver
"Alcance reducido" más abajo).

### Fuente elegida y por qué (no AEMET)

El objetivo de la tarea sugería tanto esta fuente municipal como AEMET
OpenData. Se eligió la fuente de datos.madrid.es porque **no requiere
ninguna credencial** (AEMET OpenData sí exige una API key gratuita con
registro) y ya cubre el objetivo (temperatura, humedad, viento,
precipitación...) sin ese paso adicional.

### Formato real encontrado

Este dataset usa el mismo backend "bdca" (Servicio de Calidad del Aire) que
`calidad_aire_madrid.py` (tarea 006), documentado en el mismo tipo de PDF
("Intérprete de ficheros de datos meteorológicos horarios – diarios y
tiempo real" que publica el propio dataset): no es una lista plana de
lecturas, sino un registro por combinación estación+magnitud+día, con las
24 lecturas horarias de ese día ya embebidas en columnas `H01`..`H24` (cada
una con su código de validación `V01`..`V24`). A diferencia del JSON de
calidad del aire, aquí no hay campo `PUNTO_MUESTREO`: el código de estación
es directamente el campo `ESTACION` (p.ej. `"102"`), que coincide con la
columna `CÓDIGO_CORTO` del catálogo de estaciones.

Códigos de magnitud (Anexo II del PDF): `80` radiación ultravioleta
(Mw/m2), `81` velocidad de viento (m/s), `82` dirección de viento (sin
unidad según el PDF — se asume grados), `83` temperatura (ºC), `86`
humedad relativa (%), `87` presión barométrica (mb), `88` radiación solar
(W/m2), `89` precipitación (l/m2). No todas las estaciones miden todas las
magnitudes (el catálogo marca con `X` cuáles).

El JSON de tiempo real no incluye nombre, dirección ni coordenadas de la
estación (solo su código corto), así que esta captura hace una segunda
descarga al dataset "Datos meteorológicos. Estaciones de control" (id
`300360-0-meteorologicos-estaciones`), un CSV con esos metadatos —
mismo patrón de dos fuentes combinadas que `calidad_aire_madrid.py` y
`ruido_madrid.py`. Ese catálogo ya publica `LONGITUD`/`LATITUD` en WGS84
decimal con punto (no hace falta ninguna corrección de formato, a
diferencia del catálogo de ruido de la tarea 007).

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

A diferencia de `calidad_aire_madrid.py` (un registro por magnitud), cada
registro normalizado aquí agrega **todas las magnitudes de una misma
estación** en un único registro (temperatura, humedad, viento, presión,
radiación, precipitación como columnas): el objetivo de la tarea pide
explícitamente un esquema con "temperatura, humedad, viento, precipitación"
como campos de un mismo registro, no un registro por magnitud.

### Alcance reducido respecto a `trafico_madrid.py`

Igual que en las tareas 003-007, todavía no se ha aplicado la
infraestructura AWS (tarea 001), así que este productor, a propósito:

- **No** tiene modo `--interval-seconds` ni bucle: cada invocación hace
  exactamente una captura y termina.
- **No** escribe en la capa Bronze particionada (`BronzeWriter`): escribe un
  único fichero de muestra pequeño (como mucho `MADRID_WEATHER_SAMPLE_SIZE`,
  5 por defecto, de las ~25 estaciones de la red completa) en una ruta fija,
  pensado para commitearse como fixture, no para acumularse en disco.

### Ejecutar

```bash
python3 -m ingesta.capturas.meteorologia_madrid
```

Escribe la muestra en `ingesta/capturas/samples/meteorologia_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                       | Por defecto                                     | Descripción                                                |
| -------------------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| `MADRID_WEATHER_REALTIME_URL`  | URL del recurso JSON de tiempo real (ver módulo)  | URL del JSON de lecturas horarias en tiempo real.            |
| `MADRID_WEATHER_STATIONS_URL`  | URL del recurso CSV de estaciones (ver módulo)    | URL del CSV del catálogo de estaciones meteorológicas.       |
| `MADRID_WEATHER_SAMPLE_SIZE`   | `5`                                                 | Nº máximo de estaciones (una por registro) en la muestra.    |
| `HTTP_TIMEOUT_SECONDS`         | `15`                                                | Timeout por request HTTP.                                    |
| `HTTP_MAX_RETRIES`             | `3`                                                 | Reintentos ante fallo de red (backoff lineal simple).        |
| `HTTP_RETRY_BACKOFF_SECONDS`   | `2`                                                 | Base del backoff entre reintentos (segundos * intento).      |
| `LOG_LEVEL`                    | `INFO`                                              | Nivel de logging (también configurable con `--log-level`).   |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_meteorologia",
  "station_id": "28079102",
  "station_name": "J.M.D. Moratalaz",
  "station_address": "C/ Fuente Carantona, 8",
  "measured_at": "2026-08-12T00:00:00+00:00",
  "ingested_at": "2026-08-12T01:49:00.436260+00:00",
  "temperature_c": 25.6,
  "humidity_pct": 19.0,
  "wind_speed_ms": 1.0,
  "wind_direction_deg": 73.0,
  "pressure_mb": 941.0,
  "solar_radiation_wm2": 0.0,
  "uv_radiation_mwm2": null,
  "precipitation_lm2": 0.0,
  "location": {"lat": 40.398611, "lon": -3.636944, "srid": "EPSG:4326", "altitude_m": 686}
}
```

- Cada registro es un único instante por **estación**, con todas las
  magnitudes que reporta esa estación como columnas (`null` si la estación
  no mide esa magnitud, p.ej. `uv_radiation_mwm2` en la mayoría de
  estaciones de esta red).
- `measured_at`: la hora válida más reciente entre todas las magnitudes de
  la estación (hora de Madrid convertida a UTC). En la práctica, una misma
  estación actualiza todas sus magnitudes a la vez, así que suele coincidir
  para todos los campos de un mismo registro.
- `ingested_at`: instante en que este productor consultó ambas fuentes
  (UTC).
- `station_name`/`station_address`/`location`: `null` si el código corto de
  estación de la lectura no aparece en el catálogo descargado (no debería
  ocurrir en condiciones normales, pero se normaliza así en vez de
  descartar la lectura, mismo criterio que en el resto de capturas).
- `location.lat`/`location.lon`: coordenadas del catálogo de estaciones ya
  en WGS84 decimal, no UTM.

### Nota sobre el acceso desde este entorno (tarea 008)

Igual que en las tareas 004-007, fue posible completar una captura real en
vivo: el fixture commiteado en
`ingesta/capturas/samples/meteorologia_madrid_sample.json` son 5 estaciones
reales (J.M.D. Moratalaz, E.D.A.R. La China, Centro Mpal. De Acústica,
J.M.D. Hortaleza, Peñagrande), descargadas ejecutando el script tal cual
contra ambos recursos públicos durante esta sesión — no son datos de
ejemplo generados a mano.

## `capturas/callejero_madrid.py` — Callejero y grafo viario de Madrid (carga batch puntual, referencia)

Descarga el callejero vigente del Ayuntamiento de Madrid — viales y sus
cruces con otros viales — y lo normaliza a un esquema mínimo pensado para
alimentar más adelante el grafo urbano en Neo4j (ver `documents/Memoria_TFM
FV.docx`, apartado 5.2).

### Esto es una carga puntual de referencia, no una captura periódica

A diferencia de `transporte_publico_madrid.py`, `bicimad.py`,
`aparcamientos_madrid.py`, `calidad_aire_madrid.py`, `ruido_madrid.py` y
`meteorologia_madrid.py` (tareas 003-008), que son capturas de muestra
*reducidas* solo porque todavía no existe infraestructura AWS donde
aterrizar datos en volumen, aquí la razón es otra: el callejero de Madrid es
un dato de **referencia** que apenas cambia (el propio dataset se actualiza
"diariamente" solo para incorporar aprobaciones puntuales de nuevos viales o
cambios de numeración, no para reflejar un estado que varía por sí solo,
como sí hace el tráfico o la calidad del aire). No tiene sentido programar
su recaptura ni siquiera cuando exista infraestructura real: por eso este
módulo, igual que los anteriores, **no tiene modo `--interval-seconds` ni
bucle**, pero aquí es una decisión permanente, no temporal. La carga
completa real, el día que se aplique la infraestructura de la tarea 001,
seguirá siendo una carga batch puntual invocada a mano cuando haga falta
(p.ej. tras una actualización relevante del callejero oficial), no un
productor en bucle.

### Fuente elegida y por qué

Dataset "Callejero. Información adicional asociada. Códigos postales, zonas
SER, categoría fiscal, parcela catastral, etc." (id `200075-0-callejero`) de
[datos.madrid.es](https://datos.madrid.es/dataset/200075-0-callejero), en
concreto dos de sus recursos CSV:

- **"Viales oficiales y topónimos"**: un registro por vial vigente (calle,
  avenida, plaza...) con su código, nombre, tipo, distritos que atraviesa,
  código(s) postal(es), y las coordenadas de inicio y fin del vial — el
  **nodo** del grafo viario.
- **"Cruces de viales con coordenadas geográficas"**: un registro por cada
  cruce/enlace de un vial con otro vial, con la coordenada del cruce — la
  **arista** del grafo viario (qué vial conecta con qué otro vial, y dónde).

Se descartaron otras alternativas encontradas en la investigación:

- **"Callejero oficial del Ayuntamiento de Madrid"** (id
  `213605-0-callejero-oficial-madrid`): mismo origen (sistema CADMA), pero
  sus CSV de "viales vigentes" no incluyen coordenadas de inicio/fin ni
  cruces — solo intervalos de numeración por distrito/barrio. Podría servir
  a una futura tarea de direcciones/geocodificación, pero no da la topología
  del grafo viario que pide esta tarea.
- **"Callejero oficial. Viales vigentes"** (id `300735-0-mapas-callejero-viales`):
  solo expone un servicio WMS (mapa renderizado), sin un recurso descargable
  con la topología vial/cruces en un formato tabular simple.
- **"Callejero Oficial del Ayuntamiento de Madrid (Servicio Web)"** (id
  `300274-0-callejero-oficial-webservice`): un servicio SOAP pensado para
  sincronizar *cambios* incrementales del callejero desde sistemas externos,
  no para una carga inicial de referencia.

Se ha verificado en vivo desde este entorno que ambos recursos elegidos son
accesibles **sin ninguna autenticación ni API key**.

### Formato real encontrado

Ambos CSV se publican en **ISO-8859-1 (Latin-1)** con `;` como separador (a
diferencia del UTF-8 de calidad del aire/meteorología). Las coordenadas
WGS84 vienen como texto en formato grados-minutos-segundos con el símbolo
`º` (p.ej. `"3º40'16.72'' W"`, `"40º30'55.78'' N"`), no como decimal — este
módulo las convierte a grados decimales. El "Código de vía" (p.ej.
`"00000127"`) es el identificador estable que enlaza ambos ficheros (un
vial en "Viales" con sus cruces en "Cruces"), y se conserva tal cual como
`vial_id` (cadena de 8 dígitos con ceros a la izquierda) para no perder esa
capacidad de cruce con la fuente oficial ni con una futura carga completa.

El campo "Distritos atravesados" puede traer varios códigos separados por
`-` (p.ej. `"18-20-21"`); se normaliza a una lista. El campo "Códigos
postales" puede ser un único código, el literal `"varios"` (la fuente no
detalla cuáles cuando un vial tiene más de uno), o estar vacío — se conserva
tal cual como texto, sin inventar una lista que la fuente no da.

El CSV de cruces trae cada cruce **dos veces** (una vez con cada vial como
"tratado", en direcciones opuestas); este módulo solo conserva los cruces
cuyo vial "tratado" es uno de los viales de la muestra, para no duplicar la
misma arista dos veces.

### Ejecutar

```bash
python3 -m ingesta.capturas.callejero_madrid
```

Escribe dos ficheros de muestra (uno de viales/nodos, otro de cruces/
aristas) en `ingesta/capturas/samples/callejero_madrid_vias_sample.json` y
`ingesta/capturas/samples/callejero_madrid_cruces_sample.json`
(configurables con `--out-vias`/`--out-cruces`). No requiere ninguna
variable de entorno de credenciales.

### Variables de entorno

| Variable                              | Por defecto                                             | Descripción                                                          |
| --------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------ |
| `MADRID_STREETS_VIAS_URL`             | URL del CSV de viales (ver módulo)                       | URL del CSV de viales oficiales vigentes.                             |
| `MADRID_STREETS_CROSSINGS_URL`        | URL del CSV de cruces (ver módulo)                       | URL del CSV de cruces de viales.                                       |
| `MADRID_STREETS_SAMPLE_SIZE`          | `5`                                                        | Nº de viales (nodos) incluidos en la muestra.                          |
| `MADRID_STREETS_MAX_CROSSINGS_PER_VIAL` | `8`                                                       | Nº máximo de cruces (aristas) por vial de la muestra.                  |
| `HTTP_TIMEOUT_SECONDS`                | `30`                                                        | Timeout por request HTTP (más alto que el resto: los CSV pesan varios MB). |
| `HTTP_MAX_RETRIES`                    | `3`                                                         | Reintentos ante fallo de red (backoff lineal simple).                  |
| `HTTP_RETRY_BACKOFF_SECONDS`          | `2`                                                         | Base del backoff entre reintentos (segundos * intento).                |
| `LOG_LEVEL`                           | `INFO`                                                      | Nivel de logging (también configurable con `--log-level`).             |

### Esquema normalizado

Viales (nodos), un registro por vial:

```json
{
  "schema_version": 1,
  "source": "madrid_callejero_vias",
  "vial_id": "00000127",
  "class": "CALLE",
  "particle": "DE",
  "name": "ISABEL COLBRAND",
  "full_name": "CALLE DE ISABEL COLBRAND",
  "type": "Vía",
  "situation": "Nivel",
  "district_codes": ["08"],
  "postal_code": "28050",
  "ine_code": "00011704",
  "address_count": 52,
  "ingested_at": "2026-08-12T22:38:10.689040+00:00",
  "start_node": {"lat": 40.515494, "lon": -3.671311, "srid": "EPSG:4326"},
  "end_node": {"lat": 40.509358, "lon": -3.680669, "srid": "EPSG:4326"}
}
```

Cruces (aristas), un registro por cruce de un vial de la muestra con otro:

```json
{
  "schema_version": 1,
  "source": "madrid_callejero_cruces",
  "from_vial_id": "00000127",
  "from_vial_name": "CALLE DE ISABEL COLBRAND",
  "to_vial_id": "00002792",
  "to_vial_name": "CALLE DE CASTIELLO DE JACA",
  "ingested_at": "2026-08-12T22:38:10.689040+00:00",
  "location": {"lat": 40.510047, "lon": -3.678731, "srid": "EPSG:4326"}
}
```

- `vial_id`/`from_vial_id`/`to_vial_id`: código de vía de 8 dígitos, tal
  como lo publica la fuente (no se convierte a entero, para no perder los
  ceros a la izquierda ni la capacidad de cruce entre ficheros).
- `type`: `"Vía"` (calle, plaza... con recorrido) o `"Topónimo"` (un punto
  singular sin recorrido, p.ej. una plaza sin nombre de calle asociado).
- `district_codes`: lista de códigos de distrito que atraviesa el vial
  (puede tener más de uno).
- `postal_code`: un único código, el literal `"varios"` si el vial tiene
  más de uno (la fuente no los detalla), o `null` si no consta.
- `start_node`/`end_node`: coordenadas de inicio/fin del vial (WGS84,
  decimal), convertidas del formato grados-minutos-segundos de la fuente.
  Viales sin coordenadas conocidas (p.ej. algunos topónimos) se descartan de
  la muestra de viales (no aportarían un nodo útil al grafo).
- `location` (en cruces): coordenada del punto de cruce entre los dos
  viales (WGS84, decimal).
- No hay `barrio` (solo `district_codes`, a nivel distrito): ninguno de los
  dos recursos usados publica el barrio del vial completo (sí lo hacen a
  nivel de tramo/numeración concreta en otros recursos del dataset, fuera
  del alcance de esta tarea).

### Nota sobre el acceso desde este entorno (tarea 009)

Se completó una **captura real en vivo**: los fixtures commiteados
(`ingesta/capturas/samples/callejero_madrid_vias_sample.json` y
`callejero_madrid_cruces_sample.json`) son 5 viales reales (Isabel Colbrand,
González Dávila, de la Abada, de los Abades, de la Abadesa) con sus 20
cruces reales, descargados ejecutando el script tal cual contra ambos
recursos públicos durante esta sesión — no son datos de ejemplo generados a
mano. El CSV de viales tenía 10.093 viales vigentes y el de cruces 31.654
cruces en el momento de la captura; ambos se descargaron completos en
memoria para poder elegir la muestra (no hay un recurso "solo los primeros
N"), pero en ningún momento se escribió el dataset completo a disco — solo
la muestra pequeña final.

## `capturas/barrios_distritos_madrid.py` — Límites administrativos de barrios y distritos de Madrid (carga batch puntual, referencia)

Descarga los límites (geometría) de los 21 distritos y 131 barrios del
municipio de Madrid, y los normaliza a un esquema mínimo pensado para
relacionar el resto de fuentes de este proyecto (tráfico, calidad del aire,
ruido...) con una unidad geográfica administrativa común.

### Esto es una carga puntual de referencia, no una captura periódica

Igual que `callejero_madrid.py` (tarea 009), los límites administrativos son
un dato de **referencia** que apenas cambia (una redelimitación de
barrios/distritos es un evento excepcional). Este módulo, a propósito, **no
tiene modo `--interval-seconds` ni bucle**, y esta es una decisión
permanente, no temporal por falta de infraestructura.

### Fuente elegida y por qué

Los datasets "Distritos municipales de Madrid" (id
`300497-0-distritos-municipales-madrid`) y "Barrios municipales de Madrid"
(id `300496-0-barrios-madrid`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300497-0-distritos-municipales-madrid)
publican varios formatos (KML, XLSX, CSV, ZIP/SHP), pero ninguno es a la vez
ligero y consultable de forma parcial: el CSV/XLSX no traen geometría (solo
id, nombre y área); el KML de distritos trae la geometría como `LineString`
(el contorno, no un polígono relleno) y hay que descargarlo completo; el KML
de barrios no fue accesible durante esta sesión (`Barrios.kml` redirige a
`indexServicioNoDisponible.html`, una página de mantenimiento genérica del
Ayuntamiento — el mismo tipo de problema de disponibilidad puntual del
portal ya visto en la tarea 009).

En su lugar, uno de los recursos listados del dataset de distritos apunta
(con el formato mal etiquetado como "CSV" en el catálogo, un error de
metadatos del propio Ayuntamiento) a un servicio **ArcGIS REST (MapServer)**
público:
<https://sigma.madrid.es/hosted/rest/services/CARTOGRAFIA/LIMITES_ADMINISTRATIVOS/MapServer>,
con capas de polígonos reales ("DISTRITOS" capa 26, "BARRIOS" capa 25, del
grupo de escalas "10.000-500", el más detallado del servicio). Se prefirió
a los ficheros KML/ZIP por dos motivos:

1. Devuelve **GeoJSON con polígonos reales**, ya reproyectados a WGS84
   (`outSR=4326`) con un simple parámetro de query — sin parsear coordenadas
   DMS (a diferencia del callejero, tarea 009) ni añadir una dependencia de
   geoprocesado (`pyproj`/`shapely`) para reproyectar desde el CRS nativo del
   servicio (ETRS89/UTM, EPSG:25830).
2. Admite **filtrar, ordenar y limitar resultados en el servidor** (`where`,
   `orderByFields`, `resultRecordCount`): esta captura pide directamente "los
   N distritos ordenados por código" o "los barrios de estos distritos", sin
   descargar nunca el conjunto completo (21 distritos / 131 barrios) a este
   entorno, ni siquiera en memoria — a diferencia de `callejero_madrid.py` o
   `ruido_madrid.py`, que sí tuvieron que descargar un CSV completo porque su
   fuente no ofrecía filtrado remoto.

Se ha verificado en vivo desde este entorno que el servicio MapServer es
accesible **sin ninguna autenticación ni API key**.

### Simplificación de la geometría

Algunos distritos tienen miles de vértices sin simplificar (Fuencarral - El
Pardo, el mayor, tiene 2.910 puntos en su polígono) — no sería un problema
para una carga completa real, pero sí inflaría una muestra pensada para ser
pequeña. Este módulo aplica una simplificación **Douglas-Peucker** (implementación
propia, sin dependencias adicionales) a cada anillo del polígono, con
tolerancia configurable (`MADRID_BOUNDARIES_SIMPLIFY_TOLERANCE_DEG`, por
defecto `0.0001` grados, ~8-11 m en la latitud de Madrid): con este valor,
Fuencarral - El Pardo pasa de 2.910 a ~450 puntos conservando la forma
general. Cada registro guarda `simplified`/`simplify_tolerance_deg` para
dejar explícito que la geometría no es necesariamente bit a bit la de la
fuente; poner la tolerancia a `0` desactiva la simplificación.

### Ejecutar

```bash
python3 -m ingesta.capturas.barrios_distritos_madrid
```

Escribe dos ficheros de muestra (uno de distritos, otro de barrios) en
`ingesta/capturas/samples/barrios_distritos_madrid_distritos_sample.json` y
`ingesta/capturas/samples/barrios_distritos_madrid_barrios_sample.json`
(configurables con `--out-distritos`/`--out-barrios`). No requiere ninguna
variable de entorno de credenciales.

### Variables de entorno

| Variable                                     | Por defecto                                 | Descripción                                                          |
| ----------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------ |
| `MADRID_BOUNDARIES_SERVICE_URL`               | URL del MapServer (ver módulo)               | URL base del servicio ArcGIS REST.                                     |
| `MADRID_BOUNDARIES_DISTRICTS_LAYER_ID`        | `26`                                           | ID de la capa "DISTRITOS" dentro del MapServer.                        |
| `MADRID_BOUNDARIES_NEIGHBOURHOODS_LAYER_ID`   | `25`                                           | ID de la capa "BARRIOS" dentro del MapServer.                          |
| `MADRID_BOUNDARIES_DISTRICT_SAMPLE_SIZE`      | `3`                                            | Nº de distritos incluidos en la muestra.                               |
| `MADRID_BOUNDARIES_MAX_NEIGHBOURHOODS_PER_DISTRICT` | `2`                                      | Nº máximo de barrios por cada distrito de la muestra.                  |
| `MADRID_BOUNDARIES_SIMPLIFY_TOLERANCE_DEG`    | `0.0001`                                       | Tolerancia (grados) de la simplificación Douglas-Peucker; `0` la desactiva. |
| `HTTP_TIMEOUT_SECONDS`                        | `15`                                            | Timeout por request HTTP.                                              |
| `HTTP_MAX_RETRIES`                            | `3`                                              | Reintentos ante fallo de red (backoff lineal simple).                  |
| `HTTP_RETRY_BACKOFF_SECONDS`                  | `2`                                              | Base del backoff entre reintentos (segundos * intento).                |
| `LOG_LEVEL`                                   | `INFO`                                           | Nivel de logging (también configurable con `--log-level`).             |

### Esquema normalizado

Distritos, un registro por distrito:

```json
{
  "schema_version": 1,
  "source": "madrid_distritos",
  "district_id": "01",
  "name": "Centro",
  "area_m2": 5228245.50873203,
  "ingested_at": "2026-08-12T22:47:59.275940+00:00",
  "simplified": true,
  "simplify_tolerance_deg": 0.0001,
  "geometry": {"type": "Polygon", "coordinates": [[[-3.693, 40.407], ...]], "srid": "EPSG:4326"}
}
```

Barrios, un registro por barrio:

```json
{
  "schema_version": 1,
  "source": "madrid_barrios",
  "neighbourhood_id": "011",
  "name": "Palacio",
  "district_id": "01",
  "district_name": "Centro",
  "area_m2": 1469905.932620575,
  "ingested_at": "2026-08-12T22:47:59.275940+00:00",
  "simplified": true,
  "simplify_tolerance_deg": 0.0001,
  "geometry": {"type": "Polygon", "coordinates": [[[-3.705, 40.420], ...]], "srid": "EPSG:4326"}
}
```

- `district_id`/`neighbourhood_id`: códigos oficiales tal como los publica la
  fuente (`COD_DIS_TX`, dos dígitos; `COD_BAR`, tres dígitos), como cadenas
  (no se convierten a entero, para no perder ceros a la izquierda).
- `area_m2`: área del polígono tal como la calcula el propio servicio
  (`Shape.STArea()`), en metros cuadrados.
- `geometry`: GeoJSON `Polygon` (o `MultiPolygon` si la fuente alguna vez
  devolviera un distrito/barrio con varias partes; no ha ocurrido en la
  investigación de esta tarea — los 21 distritos y 131 barrios actuales son
  todos `Polygon` simples), ya en WGS84 (`EPSG:4326`), tras la simplificación
  Douglas-Peucker si `simplify_tolerance_deg` no es `null`.
- La muestra de barrios está acotada a los distritos que también están en la
  muestra de distritos (mismo criterio de "grafo padre-hijo coherente" que
  viales/cruces en `callejero_madrid.py`, tarea 009): no aparecerá un barrio
  cuyo distrito no esté también en el fixture.

### Nota sobre el acceso desde este entorno (tarea 010)

Se completó una **captura real en vivo**: los fixtures commiteados
(`ingesta/capturas/samples/barrios_distritos_madrid_distritos_sample.json` y
`barrios_distritos_madrid_barrios_sample.json`) son 3 distritos reales
(Centro, Arganzuela, Retiro) con 2 barrios reales cada uno (Palacio,
Embajadores; Imperial, Acacias; Pacífico, Adelfas), descargados ejecutando
el script tal cual contra el servicio ArcGIS REST público durante esta
sesión — no son datos de ejemplo generados a mano. A diferencia de las
tareas anteriores, en ningún momento se descargó el conjunto completo (ni
siquiera a memoria): el propio servicio filtra, ordena y limita los
resultados a petición.

## `capturas/poi_madrid.py` — Puntos de interés turístico de Madrid (carga batch puntual, referencia)

Descarga el catálogo de puntos de interés turístico del Ayuntamiento de
Madrid y lo normaliza a un esquema mínimo pensado para que el asistente
conversacional resuelva preguntas como «¿merece la pena ir a X lugar?» (ver
`documents/Memoria_TFM FV.docx`, apartado 6.1, categoría «Contexto urbano»:
puntos de interés).

### Esto es una carga puntual de referencia, no una captura periódica

Igual que `callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py`
(tarea 010), la ficha de un monumento o museo es un dato de **referencia**
que no cambia minuto a minuto. Este módulo, a propósito, **no tiene modo
`--interval-seconds` ni bucle**, y esta es una decisión permanente, no
temporal por falta de infraestructura.

### Fuente elegida y por qué: una sola categoría, "Edificios y monumentos"

Dataset "Puntos de interés turístico de la ciudad de Madrid. Qué visitar en
Madrid (www.esmadrid.com)" (id `300030-0-puntos-interes-turistico`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300030-0-puntos-interes-turistico),
publicado por Madrid Destino. Un único XML con 935 fichas (museos,
monumentos, salas de exposiciones, parques, instalaciones
culturales/deportivas...), cada una con descripción, geoposición, dirección,
horario y coste de acceso.

Se descartaron dos alternativas: "Edificios de carácter monumental" (id
`208844-0-monumentos-edificios`, listado más estrecho, sin descripción
turística ni horarios/precios) y "Planeamiento Urbanístico. Catálogo de
Elementos Singulares" (id `300486-0-planeamiento-elemento-singulares`,
dataset de protección patrimonial, no de contenido turístico).

El XML clasifica cada ficha con una o varias categorías. Sobre las 935
fichas totales: 395 "Instalaciones culturales", 355 "Edificios y
monumentos", 63 "Parques y jardines", 40 "Parques y centros de ocio", 31
"Empresas de guías turísticos", 25 "Otros", 21 "Espacios para eventos", 20
"Servicios", 13 "Instalaciones deportivas", 11 "Escuelas de cocina y catas
de vinos y aceites", 8 "Cotrabajo", 4 "Consignas" (una ficha puede tener más
de una categoría). Se eligió **una única categoría, "Edificios y
monumentos"** (`idCategoria` `7173`): es la que más directamente encaja con
"monumentos y lugares de interés turístico" (el ejemplo del objetivo de la
tarea) y con la pregunta guía «¿merece la pena ir a X lugar?», a diferencia
de categorías como "Empresas de guías turísticos" o "Servicios" (agencias,
no lugares que visitar). Todas las categorías comparten el mismo esquema
XML, así que una tarea futura de carga completa puede iterar sobre el resto
de categorías reutilizando este módulo sin cambios de esquema.

Se ha verificado en vivo desde este entorno que el recurso es accesible
**sin ninguna autenticación ni API key**. El servidor `esmadrid.com` sí
devuelve `403 Forbidden` a peticiones sin cabecera `User-Agent` o con la que
usan por defecto `requests`/`curl -A` (un filtro básico anti-bot, no una
restricción de acceso real); este módulo declara un `User-Agent` de
navegador convencional para evitarlo.

### Licencia: textos libres, fotografías no

El dataset advierte de condiciones de uso específicas: *"Los textos son de
libre uso pero no así las fotografías"*. Por eso este módulo, a propósito,
**no incluye las URLs de `<multimedia>` en el esquema normalizado**: solo
texto y metadatos, que la fuente sí permite reutilizar libremente.

### Formato real encontrado

El PDF de estructura que publica el propio dataset etiqueta
`latitude`/`longitude` como "UTM", pero los valores reales son grados
decimales WGS84 (comprobado en vivo) — un error de documentación de la
fuente. Los campos `name`/`title` traen entidades HTML **doblemente
escapadas** (p.ej. `&eacute;` literal en vez de `é`, porque la fuente
escribió `&amp;eacute;` en el XML crudo); `body`, "Horario" y "Servicios de
pago" traen HTML embebido. `_strip_html`/`_unescape` normalizan ambos casos
a texto plano.

No hay dato de **distrito ni barrio** en la fuente (solo dirección postal y
código postal, y un campo `locality` que a veces —no siempre— trae un
nombre de distrito, p.ej. `"Fuencarral - El Pardo"`, sin que la fuente lo
declare como tal ni lo rellene de forma consistente): se deja `district` y
`neighbourhood` a `null` en vez de intentar derivarlo de un campo poco
fiable. Una derivación fiable requeriría un cruce punto-en-polígono con los
límites de `barrios_distritos_madrid.py` (tarea 010), fuera del alcance de
esta captura de muestra.

### Ejecutar

```bash
python3 -m ingesta.capturas.poi_madrid
```

Escribe la muestra en `ingesta/capturas/samples/poi_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                  | Por defecto                                       | Descripción                                                |
| --------------------------- | ---------------------------------------------------- | -------------------------------------------------------------- |
| `MADRID_POI_SOURCE_URL`   | `https://www.esmadrid.com/opendata/turismo_v1_es.xml` | URL del XML de puntos de interés (español).                   |
| `MADRID_POI_CATEGORY_ID`  | `7173`                                                | `idCategoria` a incluir en la muestra ("Edificios y monumentos"). |
| `MADRID_POI_SAMPLE_SIZE`  | `5`                                                    | Nº máximo de puntos de interés que se guardan en la muestra.  |
| `HTTP_TIMEOUT_SECONDS`    | `30`                                                   | Timeout por request HTTP.                                      |
| `HTTP_MAX_RETRIES`        | `3`                                                     | Reintentos ante fallo de red (backoff lineal simple).          |
| `HTTP_RETRY_BACKOFF_SECONDS` | `2`                                                  | Base del backoff entre reintentos (segundos * intento).        |
| `LOG_LEVEL`               | `INFO`                                                  | Nivel de logging (también configurable con `--log-level`).     |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_poi_turismo",
  "poi_id": "109143",
  "name": "Comunidad Evangélica de Habla Alemana – Friedenskirche",
  "category": "Edificios y monumentos",
  "subcategories": [],
  "description": "Muy cerca de la Plaza de Colón...",
  "address": "de la Castellana, 6",
  "postal_code": "28046",
  "locality": null,
  "country": "Spain",
  "district": null,
  "neighbourhood": null,
  "website": "https://www.esmadrid.com/informacion-turistica/comunidad-evangelica-habla-alemana-friedenskirche",
  "phone": "(+34) 91 435 47 81",
  "email": "friedenskirche@friedenskirche.es",
  "schedule": "Oficina: Lun - Vier: 10:00 - 14:00 h ...",
  "price_info": "--",
  "last_updated": "2026-06-04",
  "ingested_at": "2026-08-12T22:58:17.717369+00:00",
  "location": {"lat": 40.4272094, "lon": -3.6891476, "srid": "EPSG:4326"}
}
```

- `poi_id`: identificador del punto de interés dentro de esmadrid.com (`id`
  del `<service>`).
- `category`/`subcategories`: nombre de la categoría buscada (siempre
  "Edificios y monumentos" en esta muestra) y las subcategorías asociadas a
  esa categoría concreta, si las hay (una ficha con varias categorías puede
  tener subcategorías bajo una categoría distinta a la buscada; esas no se
  incluyen).
- `description`/`schedule`/`price_info`: texto plano, sin HTML (ver "Formato
  real encontrado" más arriba). `null` si el campo viene vacío en la fuente;
  el literal `"--"` de la fuente (usado para "no aplica") se conserva tal
  cual, no se convierte a `null` (es un valor real de la fuente, no una
  ausencia de dato).
- `district`/`neighbourhood`: siempre `null` en esta fuente (no la publica;
  ver "Formato real encontrado").
- `last_updated`: fecha (`aaaa-mm-dd`, sin hora) de la última actualización
  de la ficha en el portal esmadrid.com, tal como la da la fuente.
- `ingested_at`: instante en que este productor descargó el catálogo (UTC).
- `location.lat`/`location.lon`: WGS84 decimal (pese a que el PDF de la
  fuente los etiqueta como "UTM", ver más arriba).
- Puntos sin coordenadas conocidas se descartan de la muestra (no debería
  ocurrir en la práctica — no se encontró ningún caso así en las 355 fichas
  de "Edificios y monumentos" durante la investigación de esta tarea — pero
  se comprueba por robustez).
- No se incluyen URLs de fotografías (`<multimedia>`): la licencia del
  dataset restringe su reutilización (ver "Licencia" más arriba).

### Nota sobre el acceso desde este entorno (tarea 011)

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/poi_madrid_sample.json`) son 5 puntos de interés
reales de la categoría "Edificios y monumentos" (Comunidad Evangélica de
Habla Alemana – Friedenskirche, Huerta de la Salud, Quinta del Duque del
Arco, Fuente del río Lozoya, Refugio antiaéreo del Retiro), descargados
ejecutando el script tal cual contra el recurso público durante esta
sesión — no son datos de ejemplo generados a mano. El catálogo completo
(935 fichas, ~3.6 MB) se descargó en memoria porque la fuente no ofrece
filtrado remoto por categoría, pero en ningún momento se escribió a disco;
solo la muestra final de 5 puntos.

## `capturas/afluencia_lugares_madrid.py` — Afluencia de lugares de Madrid (muestra puntual, zona gris)

**Léase esta sección antes de reutilizar este módulo.** Descarga, para una
muestra pequeña de lugares conocidos de Madrid (Puerta del Sol, Parque del
Retiro, Mercado de San Miguel, Museo del Prado, Plaza Mayor), popularidad en
vivo (`live_pct`) y el patrón típico de afluencia por día de la semana y hora
(`typical_by_hour`), para que el asistente conversacional pueda responder
tanto «¿está muy lleno esto ahora?» como «¿un viernes a las 21h suele haber
mucha gente aquí?» (ver `documents/Memoria_TFM FV.docx`, apartado 6.1
«Contexto urbano»: afluencia de lugares públicos).

### Origen del dato: API oficial + scraping no documentado (zona gris)

No existe ninguna API oficial que venda este dato concreto. Google no lo
expone en su API de pago (Places API); la única vía conocida y con algo de
mantenimiento es la librería
[`m-wrzr/populartimes`](https://github.com/m-wrzr/populartimes), que combina
**dos fuentes de naturaleza muy distinta** en una sola consulta:

1. La API oficial "Find Place from Text" de Google Places (de pago, con tier
   gratuito mensual), usada aquí solo para resolver el nombre de un lugar a
   su `place_id` (`resolve_place_id`).
2. Un **endpoint interno no documentado de Google**
   (`google.*/search?tbm=map...`), al que `populartimes.get_id(...)` hace
   scraping y del que parsea por posición un JSON sin contrato público, para
   obtener `current_popularity` y el patrón `populartimes` por día/hora. Es
   intrínsecamente frágil (puede romperse sin aviso si Google cambia su
   página) y su issue más comentado en GitHub es, literalmente, sobre
   posible violación de las condiciones de uso de Google.

Tal y como reconoce explícitamente la memoria de este TFM (**apartado
6.8**): esta fuente concreta usa «librerías de código abierto» en una «zona
gris» respecto a las condiciones de uso de terceros, **admisible únicamente
en el marco académico de este trabajo**. En producción, este productor se
sustituiría por un **proveedor comercial con licencia** sobre este mismo
tipo de dato (p.ej. [BestTime.app](https://besttime.app) o similar) — no se
integra en este repositorio, solo se deja constancia de la alternativa. Por
eso este módulo, a propósito, **no reimplementa el scraping a mano**: usa
`populartimes` tal cual como dependencia externa.

`populartimes` no está publicada en PyPI (verificado en vivo durante esta
sesión: `https://pypi.org/pypi/populartimes/json` devuelve `404`), así que
`ingesta/requirements.txt` la instala directamente desde GitHub:
`populartimes @ git+https://github.com/m-wrzr/populartimes`.

### Esto es una captura puntual de muestra, y debe seguir siéndolo

Igual que las tareas 003-008, este módulo **no tiene modo
`--interval-seconds` ni bucle**, y no escribe en la capa Bronze
particionada. A diferencia de esas tareas, la razón no es solo "todavía no
hay infraestructura": raspar Google en bucle agravaría el problema de zona
gris descrito arriba. Un futuro productor continuo real de este dato debería
migrar al proveedor comercial mencionado, no escalar esta técnica.

### Autenticación (API key gratuita de Google Cloud)

Se necesita una **API key de Google Maps Platform** con la "Places API"
habilitada, obtenida gratis (tier mensual gratuito) en
<https://console.cloud.google.com/google/maps-apis/credentials>: crear un
proyecto, habilitar "Places API", crear una clave de API. Se lee de
`GOOGLE_MAPS_API_KEY`, nunca hardcodeada. Los tests no la necesitan (usan una
respuesta de ejemplo de la librería, no la red).

### Ejecutar

```bash
export GOOGLE_MAPS_API_KEY="tu-api-key"
python3 -m ingesta.capturas.afluencia_lugares_madrid
```

Escribe la muestra en
`ingesta/capturas/samples/afluencia_lugares_madrid_sample.json`
(configurable con `--out`).

### Variables de entorno

| Variable                    | Por defecto                                 | Descripción                                                     |
| ---------------------------- | ---------------------------------------------- | -------------------------------------------------------------------- |
| `GOOGLE_MAPS_API_KEY`       | *(ninguno, requerido)*                          | API key de Google Maps Platform con Places API habilitada.           |
| `MADRID_PLACES_QUERIES`     | Sol, Retiro, S. Miguel, Prado, Plaza Mayor      | Lista de búsquedas de texto, separadas por `\|` (ver `DEFAULT_PLACE_QUERIES`). |
| `MADRID_PLACES_SAMPLE_SIZE` | `5`                                              | Nº máximo de lugares que se capturan (toma los primeros N de la lista). |
| `HTTP_TIMEOUT_SECONDS`      | `30`                                             | Timeout por request HTTP.                                             |
| `HTTP_MAX_RETRIES`          | `3`                                              | Reintentos ante fallo de red (backoff lineal simple).                 |
| `HTTP_RETRY_BACKOFF_SECONDS` | `2`                                             | Base del backoff entre reintentos (segundos * intento).               |
| `LOG_LEVEL`                 | `INFO`                                           | Nivel de logging (también configurable con `--log-level`).            |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "google_populartimes",
  "place_id": "ChIJi7xhMz0nQg0RVeMHylTfhY4",
  "name": "Puerta del Sol",
  "query": "Puerta del Sol, Madrid",
  "address": "Puerta del Sol, 28013 Madrid, Spain",
  "location": {"lat": 40.4169473, "lon": -3.7035285, "srid": "EPSG:4326"},
  "captured_at": "2026-08-13T12:30:00+00:00",
  "live_pct": 72,
  "typical_by_hour": {
    "lunes": [0, 0, "... 24 valores 0-100 ...", 5],
    "martes": ["..."],
    "miercoles": ["..."],
    "jueves": ["..."],
    "viernes": ["..."],
    "sabado": ["..."],
    "domingo": ["..."]
  },
  "is_mock": true
}
```

- `query`: la búsqueda de texto usada para resolver el lugar (una de
  `MADRID_PLACES_QUERIES`), conservada para trazabilidad.
- `live_pct`: popularidad en vivo en el momento de la captura, 0-100.
  `null` si Google no tiene datos suficientes para ese lugar en ese
  instante (ocurre con cierta frecuencia, sobre todo fuera de horario
  habitual o para lugares poco "comerciales" como un parque).
- `typical_by_hour`: patrón habitual, `día_en_español -> [24 valores 0-100]`
  (índice = hora del día, `0`-`23`). `null` si Google no tiene ningún patrón
  histórico para ese lugar (no todos los lugares lo tienen).
- `is_mock`: `true` si el registro es un dato de ejemplo escrito a mano (no
  proviene de una captura real), para que la procedencia quede explícita en
  el propio dato y no solo en esta documentación — ver nota siguiente.

### Nota sobre el intento de captura real en esta sesión

Este entorno **no tiene configurada ninguna `GOOGLE_MAPS_API_KEY`** (no hay
forma de completar el alta de una cuenta de Google Cloud de forma autónoma
en este pipeline, igual que el bloqueo de verificación por email de la tarea
003 con la EMT). Se verificó igualmente, en vivo y desde este entorno:

- La librería `populartimes` se instala correctamente desde GitHub
  (`pip install "populartimes @ git+https://github.com/m-wrzr/populartimes"`,
  sin errores) y expone `populartimes.get_id(api_key, place_id)`.
- `resolve_place_id` (la llamada oficial "Find Place") funciona de extremo a
  extremo contra la API real de Google: con una clave de prueba inválida,
  Google responde `200 OK` con `{"status": "REQUEST_DENIED", ...}`, que este
  módulo interpreta correctamente como "sin candidato" (se registra un
  `WARNING` y ese lugar se omite del lote, sin interrumpir la captura del
  resto).
- Con esa misma clave inválida, `populartimes.get_id(...)` lanza
  `populartimes.crawler.PopulartimesException` con el mensaje exacto
  `('Google Places REQUEST_DENIED', 'Request was denied, the API key is
  invalid.')` — el fallo esperado por falta de credencial válida, no un
  error de la librería en sí ni de este módulo.

Es decir: **la librería no falló por sí misma** durante esta sesión (el
scraping no se llegó a ejercitar por falta de una clave válida, no por
estar rota); el único bloqueo real es no disponer de una `GOOGLE_MAPS_API_KEY`
en este entorno. Por eso el fixture commiteado en
`ingesta/capturas/samples/afluencia_lugares_madrid_sample.json` son 5 lugares
con datos de ejemplo (mock) escritos a mano —cada uno con `"is_mock": true`—
que siguen exactamente el esquema que produce `normalize_record` (incluido
un lugar, Plaza Mayor, con `live_pct`/`typical_by_hour` a `null`, para dejar
constancia de ese caso realista). El código queda completo y listo para
ejecutarse tal cual el día que alguien configure una `GOOGLE_MAPS_API_KEY`
real.

## Tests

No dependen de la red: usan fixtures con copias/ejemplos de las respuestas
reales de cada fuente (`ingesta/tests/fixtures/`).

```bash
python3 -m unittest discover -s ingesta/tests -t .
```
