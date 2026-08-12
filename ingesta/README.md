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
(tarea 003), `bicimad.py` (tarea 004), `aparcamientos_madrid.py` (tarea 005)
y `calidad_aire_madrid.py` (tarea 006), que a propósito solo hacen capturas
puntuales de muestra — ver sus secciones más abajo.

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

## Tests

No dependen de la red: usan fixtures con copias/ejemplos de las respuestas
reales de cada fuente (`ingesta/tests/fixtures/`).

```bash
python3 -m unittest discover -s ingesta/tests -t .
```
