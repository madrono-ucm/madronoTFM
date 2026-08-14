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
`meteorologia_madrid.py` (tarea 008), `afluencia_lugares_madrid.py` (tarea
012), `aforos_peatones_bicicletas_madrid.py` (tarea 013),
`bluesky_menciones_madrid.py` (tarea 016), `agenda_eventos_madrid.py`
(tarea 017), `aemet_prevision_avisos.py` (tarea 018) y
`cams_calidad_aire_madrid.py` (tarea 019), que a propósito solo hacen
capturas puntuales de muestra — ver sus secciones más abajo.

`callejero_madrid.py` (tarea 009) es un caso distinto de los anteriores: no
es un dato que cambie con el tiempo (tráfico, calidad del aire...), sino un
dato de **referencia** (el callejero y grafo viario de Madrid) que apenas
varía. Por eso es, a propósito, una **carga batch puntual**, no solo una
"muestra reducida por falta de infraestructura" — nunca necesitará
programarse periódicamente, ni siquiera cuando exista infraestructura real.
`barrios_distritos_madrid.py` (tarea 010), `poi_madrid.py` (tarea 011) y
`calendario_laboral_madrid.py` (tarea 020) son del mismo tipo: los límites
administrativos de barrios y distritos, los puntos de interés turístico de
Madrid, y el calendario laboral y festivos de Madrid, también son datos de
referencia. Ver sus secciones más abajo.

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

## `capturas/bronze.py` — `BronzeWriter`: escritura en la capa Bronze (local o S3)

Todos los productores que escriben a Bronze (hoy, `trafico_madrid.py`) lo
hacen a través de esta clase común, para no repetir la lógica de
particionado en cada uno. `BronzeWriter(base_path, dataset)` elige backend
según la forma de `base_path`:

- **Local (por defecto)**: cualquier ruta que no empiece por `s3://`.
  Escribe en disco con `Path.open()`, sin cambios desde la tarea 002 — el
  modo usado en desarrollo y en todos los tests del proyecto.
- **S3** (tarea 025): rutas `s3://<bucket>/<prefijo-opcional>`. Escribe con
  `boto3` (`put_object`), usando las credenciales por defecto que resuelve
  `boto3` automáticamente — en la EC2 de ingesta, las del rol de instancia
  `madrono-tfm-dev-ingestion-role` (tarea 015), sin necesidad de configurar
  ninguna credencial explícita ni tocar código de los productores.

En ambos casos la partición es la misma:

```
<base>/<dataset>/fecha=YYYY-MM-DD/hora=HH/<timestamp>_<sufijo>.json
```

`write_batch(...)` devuelve la ubicación del objeto escrito: un `Path` en
modo local (sin cambios), o un `str` con la URI `s3://bucket/key` en modo
S3.

Para apuntar una captura al bucket Bronze real del lakehouse (tarea 001,
aplicado en la tarea 015):

```bash
export BRONZE_BASE_PATH=s3://madrono-tfm-dev-bronze-222234418587/
python3 -m ingesta.capturas.trafico_madrid
```

Esta tarea (025) deja el código de escritura en S3 listo y probado con un
doble de `boto3` (`ingesta/tests/test_bronze.py`), pero **no** ha escrito
todavía en el bucket real — activar `BRONZE_BASE_PATH=s3://...` en
producción (cron/systemd timer de cada productor) es una decisión de
despliegue posterior, fuera del alcance de esta tarea.

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
| `BRONZE_BASE_PATH`            | `./bronze`                                          | Ruta base de la capa Bronze. Local (disco) por defecto; con una URI `s3://<bucket>/<prefijo>` escribe en S3 vía `boto3` — ver sección `capturas/bronze.py` más arriba. |
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

### Autenticación (credenciales de aplicación, v1.1)

La tarea 003 asumió que la API se autentica con email + contraseña de una
cuenta personal verificada por correo (endpoint v1). Esa asunción era
incorrecta y dejó la captura bloqueada. El mecanismo real, verificado en vivo
en la tarea 024, es un login **v1.1** con credenciales de **aplicación**
(`x-ClientId` / `passKey`), no de un usuario individual — no hace falta
registrar ni verificar ninguna cuenta personal:

```
GET https://openapi.emtmadrid.es/v1.1/mobilitylabs/user/login/
Headers: x-ClientId: <client id>, passKey: <pass key>, Content-Type: application/json
```

que devuelve un `accessToken` (en `data[0].accessToken`) a reenviar en la
cabecera `accessToken` de la llamada de llegadas
(`POST /v2/transport/busemtmad/stops/{stop_id}/arrives/`, sin cambios). Las
credenciales se leen de `EMT_CLIENT_ID` / `EMT_PASS_KEY`, nunca hardcodeadas
ni registradas en logs.

La API responde con dos códigos de éxito distintos, ambos con un
`accessToken` válido en `data[0]` (verificado en vivo): `code="00"` en un
login nuevo ("Register user...") y `code="01"` cuando ya había una sesión
reciente en caché para esas credenciales y devuelve el token extendido
("Token extend..."). `fetch_access_token` acepta ambos.

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
export EMT_CLIENT_ID="tu-client-id-de-aplicación"
export EMT_PASS_KEY="tu-pass-key-de-aplicación"
python3 -m ingesta.capturas.transporte_publico_madrid --stop-id 70
```

Escribe la muestra en `ingesta/capturas/samples/transporte_publico_madrid_sample.json`
(configurable con `--out`).

### Captura real completada (tarea 024)

La tarea 003 dejó esta fuente bloqueada porque asumió el flujo v1
(email/contraseña de una cuenta personal sin verificar). La tarea 024
corrigió esa asunción: con `EMT_CLIENT_ID`/`EMT_PASS_KEY` (credenciales de
aplicación, ya provisionadas fuera del repositorio) se verificó en vivo el
flujo completo — login v1.1 y consulta de llegadas — y ambos funcionan
(`200`/`code` de éxito en los dos pasos). El fixture commiteado en
`ingesta/capturas/samples/transporte_publico_madrid_sample.json` son 5
llegadas reales descargadas con `capture_sample` a la parada 70 (elegida por
tener más líneas en servicio simultáneo que la 71 en el momento de la
captura, para una muestra más representativa), no datos inventados a mano
como en la tarea 003.

### Variables de entorno

| Variable                | Por defecto                    | Descripción                                                  |
| ------------------------ | -------------------------------- | -------------------------------------------------------------- |
| `EMT_CLIENT_ID`          | *(ninguno, requerido)*           | Client ID de aplicación MobilityLabs (credencial de app, no de usuario). |
| `EMT_PASS_KEY`           | *(ninguno, requerido)*           | Pass key de esa aplicación.                                     |
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
credenciales), **el feed GBFS de BiciMAD no requiere ninguna API key ni
registro**. Se ha verificado en vivo desde este entorno que
`station_information` y `station_status` responden sin ninguna cabecera de
autenticación. GBFS es el estándar de facto para sistemas de
bicicleta/patinete compartidos, y BiciMAD lo publica completo (674
estaciones a fecha de esta captura), así que se prefirió sobre la
alternativa de usar la API MobilityLabs de BiciMAD
(`openapi.emtmadrid.es/v1/transport/bicimad/stations/`), que sí requeriría
las mismas credenciales de aplicación que la tarea 003 asumió erróneamente
como bloqueo permanente (ver tarea 024).

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

## `capturas/aforos_peatones_bicicletas_madrid.py` — Aforos de peatones y bicicletas de Madrid (muestra puntual)

Descarga los conteos horarios de peatones y bicicletas de la red de
estaciones permanentes de aforo del Ayuntamiento de Madrid (cámaras de
visión artificial, tecnología Data From Sky) y los normaliza a un esquema
mínimo y consistente. Complementa a `afluencia_lugares_madrid.py` (tarea
012): donde esa fuente estima popularidad tipo Google para un lugar
concreto vía una librería en zona gris académica, esta usa un **dato
oficial del Ayuntamiento, sin ningún problema de condiciones de uso**
(licencia CC BY 4.0) — conteos reales en puntos y calles fijas, no una
estimación de un tercero.

### Fuente elegida y formato real encontrado

Dataset ["Aforos de peatones y bicicletas"](https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas)
(id `300321-0-aforos-peatones-bicicletas`), publicado por la Dirección
General de Planificación e Infraestructuras de Movilidad. Publica **un CSV
independiente por año y por modo** (peatones / bicicletas), verificado en
vivo vía la API CKAN del portal: 6 CSV de peatones y 6 de bicicletas
(2019-2024). Las notas internas del propio dataset explican por qué solo
hay un recurso por año en vez de uno por trimestre: se recopila
trimestralmente pero se publica como un único CSV anual acumulado, que se
sustituye trimestre a trimestre a medida que llegan datos nuevos.

A fecha de esta captura (2026-08-13), pese a que los metadatos del dataset
figuran como modificados el 2026-07-24, **el recurso más reciente sigue
siendo el de 2024** (verificado en vivo: no existe ningún recurso 2025 ni
2026), y ese propio CSV de 2024 solo cubre enero-junio (hasta el 30/06/2024
inclusive) — es un dataset con un desfase de publicación notable. Se usan
esos dos recursos (2024, uno por modo) como fuente por defecto; si en el
futuro hay un recurso más reciente, basta con apuntar
`MADRID_COUNTERS_PEDESTRIAN_URL`/`MADRID_COUNTERS_BICYCLE_URL` a la nueva
URL, sin tocar código (mismo criterio que la nota equivalente sobre
`callejero_madrid.py`, tarea 009).

Cada CSV (~17 MB peatones, ~34 MB bicicletas para 2024) trae una fila por
estación y hora, separador `;`, UTF-8 con BOM. Columnas relevantes:
`fecha` (fecha+hora local `DD/MM/YYYY H:MM`; `hora` repite solo el tramo
horario y se descarta por redundante), `identificador` (id de estación,
siempre idéntico a `device_id`, verificado sobre el fichero completo),
`peatones`/`bicicletas` (el conteo, según el fichero), `Número_distrito` y
`distrito` (vacíos en algunas estaciones, p.ej. pedanías como Barajas),
`direccion`, `observaciones_direccion`, y `latitude`/`longitude` en el
mismo formato "agrupado por puntos" que `ruido_madrid.py` (p.ej.
`"40.417.386"` → `40.417386`, no un decimal simple).

**El fichero está agrupado por estación, no por fecha** (todo el histórico
de una estación seguido, luego el de la siguiente) — a diferencia del CSV
diario de `ruido_madrid.py`, que sí es cronológico de forma global. Por eso
`parse_latest_day_rows` no puede limitarse a "cortar cuando cambia la
fecha" (el patrón usado en `ruido_madrid.py`): hace un primer recorrido
para hallar la fecha máxima real de todo el fichero y un segundo filtrado
por esa fecha. Se verificó en vivo que las 30 estaciones de peatones y las
53 de bicicletas comparten la misma última fecha (30/06/2024), así que el
resultado sigue siendo "el último día, todas las estaciones".

Ninguno de los dos CSV ofrece un recurso más pequeño ni filtrado remoto, así
que hace falta traer cada CSV completo a memoria para elegir la muestra; en
ningún momento se escribe el dataset completo en el disco de esta EC2, solo
la muestra final pequeña. Se ha verificado en vivo que ambos recursos son
accesibles **sin ninguna autenticación ni API key**.

### Dos redes de estaciones distintas, no un único punto con dos columnas

Peatones y bicicletas se miden en redes de estaciones físicamente distintas
(30 puntos permanentes de peatones, id `PERM_PEA##`; 53 de bicicletas,
`PERM_BICI##`), casi siempre en calles diferentes. Por eso cada registro
normalizado trae ambos campos `pedestrian_count`/`bicycle_count` (tal como
pedía el objetivo de la tarea), pero **solo uno de los dos está relleno por
registro** (`mode` indica cuál) — forzar un cruce por ubicación/hora para
rellenar ambos a la vez habría inventado una relación que la fuente no da.
Ambos modos comparten el mismo esquema, así que un consumidor puede tratar
la muestra como un único dataset y filtrar por `mode` si necesita solo uno.

### Esto es una captura puntual de muestra

Igual que las tareas 003-008, este módulo **no tiene modo
`--interval-seconds` ni bucle**, y no escribe en la capa Bronze
particionada: escribe una única muestra pequeña en un fichero fijo,
pensado para commitearse como fixture.

### Ejecutar

```bash
python3 -m ingesta.capturas.aforos_peatones_bicicletas_madrid
```

Escribe la muestra en
`ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`
(configurable con `--out`).

### Variables de entorno

| Variable                                  | Por defecto                                   | Descripción                                                              |
| ------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------- |
| `MADRID_COUNTERS_PEDESTRIAN_URL`          | CSV de peatones 2024 (ver `DEFAULT_PEDESTRIAN_URL`) | URL del recurso CSV de conteos de peatones.                         |
| `MADRID_COUNTERS_BICYCLE_URL`             | CSV de bicicletas 2024 (ver `DEFAULT_BICYCLE_URL`)  | URL del recurso CSV de conteos de bicicletas.                       |
| `MADRID_COUNTERS_SAMPLE_STATIONS`         | `3`                                             | Nº máximo de estaciones distintas por modo en la muestra.                |
| `MADRID_COUNTERS_SAMPLE_HOURS_PER_STATION` | `6`                                             | Nº máximo de horas del último día disponible que se toman de cada estación. |
| `HTTP_TIMEOUT_SECONDS`                    | `30`                                             | Timeout por request HTTP.                                                |
| `HTTP_MAX_RETRIES`                        | `3`                                              | Reintentos ante fallo de red (backoff lineal simple).                    |
| `HTTP_RETRY_BACKOFF_SECONDS`              | `2`                                              | Base del backoff entre reintentos (segundos * intento).                  |
| `LOG_LEVEL`                                | `INFO`                                           | Nivel de logging (también configurable con `--log-level`).               |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "madrid_aforos_peatones_bicicletas",
  "station_id": "PERM_PEA01_PM01",
  "mode": "peatones",
  "measured_at": "2024-06-29T22:00:00+00:00",
  "ingested_at": "2026-08-13T15:44:19.281996+00:00",
  "pedestrian_count": 857,
  "bicycle_count": null,
  "district_code": "1",
  "district": "Centro",
  "address": "Calle Arenal esquina San Martín",
  "address_notes": "Calle peatonal",
  "location": {"lat": 40.417386, "lon": -3.707141, "srid": "EPSG:4326"}
}
```

- `mode`: `"peatones"` o `"bicicletas"`, según la red de estaciones de
  origen del registro.
- `pedestrian_count`/`bicycle_count`: solo uno de los dos está relleno por
  registro (ver "Dos redes de estaciones distintas" más arriba).
- `district_code`/`district`: `null` en las estaciones sin distrito asignado
  en la fuente (p.ej. pedanías como Barajas).
- `location.lat`/`location.lon`: WGS84 decimal, convertidas desde el
  formato "agrupado por puntos" de la fuente.

### Nota sobre el acceso desde este entorno (tarea 013)

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`)
son 36 registros reales (3 estaciones de peatones × 6 horas + 3 estaciones
de bicicletas × 6 horas, del último día disponible en cada CSV,
30/06/2024), descargados ejecutando el script tal cual contra ambos
recursos públicos durante esta sesión — no son datos de ejemplo generados a
mano. Ambos CSV completos (~17 MB y ~34 MB) se descargaron en memoria
porque la fuente no ofrece filtrado remoto ni un recurso más pequeño, pero
en ningún momento se escribieron a disco; solo la muestra final de 36
registros.

## `capturas/bluesky_menciones_madrid.py` — Menciones de lugares de Madrid en Bluesky (dos modos, muestra puntual)

Captura menciones/opiniones públicas recientes sobre lugares de Madrid en
[Bluesky](https://bsky.app), como señal de "qué se dice ahora mismo (o en la
última hora/día) de un sitio" para el asistente conversacional (ver
`documents/Memoria_TFM FV.docx`, apartado 6.7: «¿voy al centro a las nueve
de la noche del viernes?»).

### Por qué Bluesky (y no Twitter/X, Mastodon o datos de operadora)

Twitter/X se descartó por no tener API de lectura gratuita viable. Se
investigaron y descartaron dos alternativas antes de elegir Bluesky:

- **Mastodon/Fediverso**: sin búsqueda unificada (cada instancia es un
  servidor independiente), muy fragmentado, y con mucha menor cobertura en
  español que Bluesky para contenido sobre Madrid.
- **CAMARA/Telefónica Population Density Data**: API de operadora móvil
  todavía "under review" en el catálogo CAMARA, exige un partner comercial y
  consentimiento por usuario final — no es autoservicio, incompatible con
  un productor de captura autónomo como los de este proyecto.

**Bluesky** tiene una API pública de lectura
(`app.bsky.feed.searchPosts`), gratis, **sin API key ni registro**, sin
límite de rate documentado para lectura pública — la fuente elegida.

### Dos modos, un mismo esquema normalizado

- **`search_place(config, query, tags=None, lang="es", since=None, ...)`**:
  búsqueda puntual por lugar/hashtag concretos (`mode="bajo_demanda"` en el
  registro resultante). Pensada para que el **asistente conversacional** la
  invoque en tiempo de consulta cuando no tenga información de un lugar que
  el usuario menciona — esta tarea implementa la función reutilizable, **no
  la despliega como servicio**.
- **`search_district_sweep(config, districts, lang="es", since=None, ...)`**:
  recorre una lista de distritos de Madrid con una búsqueda por cada uno,
  más una tanda de búsquedas genéricas de "eventos Madrid" con términos
  positivos y negativos (`concierto`, `fiesta`, `recomendación`, `queja`,
  `aglomeración`, `incidencia` — `mode="distrito_sweep"`). Pensada para un
  **productor programado cada hora** (cuando exista scheduling) que nutra
  una serie histórica agregada por zona y hora para entrenamiento del
  modelo, no para responder una pregunta puntual del asistente.

Los 21 distritos por defecto (`DEFAULT_DISTRICTS`) se obtuvieron en vivo del
mismo servicio ArcGIS que usa `barrios_distritos_madrid.py` (tarea 010),
para no adivinar la grafía oficial (p.ej. `"Fuencarral - El Pardo"`, con
espacios alrededor del guion).

Ambas funciones reciben `config: CaptureConfig` como primer argumento (igual
que `resolve_place_id`/`fetch_populartimes` en `afluencia_lugares_madrid.py`),
para mantener el mismo patrón que el resto de `ingesta/capturas/` en vez de
leer variables de entorno dentro de la propia función.

### Privacidad: sin identificadores de autor

La memoria del proyecto (apartado 6.8) exige que «las señales de discurso
social se tratan de forma agregada, sin almacenar identificadores». Por eso
`normalize_post` **descarta explícitamente** todo el bloque `author` de la
respuesta (`did`, `handle`, `displayName`, `avatar`...) y también `uri`/`cid`
del post — el `uri` de Bluesky (`at://did:plc:.../app.bsky.feed.post/...`)
**incluye el DID del autor**, así que conservarlo equivaldría casi a
conservar el identificador directamente.

Se decidió conservar el **texto literal** del post (`text`), no un hash: es
contenido ya público (visible para cualquiera en la app), y es la señal que
hará falta para una futura clasificación de sentimiento en Silver/Gold
(fuera del alcance de esta tarea). Lo que se excluye es todo lo que
identifique a quién lo escribió, no el contenido en sí. Se añade
`post_hash` (SHA-256 truncado a 16 caracteres del texto) como clave de
deduplicación barata entre términos de búsqueda solapados (p.ej. un mismo
post puede aparecer tanto en la búsqueda de un distrito como en la de un
término de evento), sin depender del `uri` real del post.

### Sin clasificación de sentimiento

Este módulo solo captura y normaliza: no etiqueta "bueno"/"malo" ni hace
ningún análisis de sentimiento — es una transformación de Silver/Gold, fuera
de alcance de un productor de Bronze (mismo criterio que el resto de
`ingesta/capturas/`).

### Host real usado: `api.bsky.app`, no `public.api.bsky.app`

El host documentado por el AT Protocol para lectura pública sin
autenticación es `https://public.api.bsky.app`. Se verificó en vivo desde
este entorno que **ese host bloquea con un 403 (WAF de BunnyCDN, página
HTML, no JSON) específicamente la llamada `app.bsky.feed.searchPosts`**,
mientras que otros métodos de solo lectura en el mismo host
(`app.bsky.actor.searchActors`, `app.bsky.unspecced.getPopularFeedGenerators`,
`/xrpc/_health`) responden `200` con normalidad. El bloqueo persistió
cambiando `User-Agent` y añadiendo cabeceras de navegador (`Accept`,
`Origin`, `Referer`) — apunta a un bloqueo específico de esa ruta para el
rango de IP de esta EC2 (probablemente porque `searchPosts` es el endpoint
más costoso de servir y el más atractivo para scraping masivo). En cambio,
`https://api.bsky.app` — el mismo host que usa la propia web `bsky.app` para
sus peticiones al AppView — expone la **misma operación, con la misma
respuesta**, y sí responde `200` desde este entorno, verificado en vivo
repetidamente durante esta sesión. Por eso este módulo usa
`https://api.bsky.app` como valor por defecto de `BLUESKY_API_BASE_URL`,
configurable por si en otro entorno (p.ej. la máquina donde corra el
asistente en producción) `public.api.bsky.app` sí funciona.

### Sin autenticación

No requiere ninguna variable de entorno de credenciales: `searchPosts` es un
endpoint de lectura pública sin API key ni registro.

### Sin despliegue: ni cron, ni bucle, ni servicio

Igual que las tareas 003-008, 012 y 013, este módulo **no tiene modo
`--interval-seconds` ni bucle**. A diferencia de esas tareas, aquí ninguno
de los dos modos se despliega tampoco como lo que serían en producción
(cron/scheduler para `search_district_sweep`, servicio del asistente para
`search_place`): esta tarea solo implementa y prueba ambas funciones, y
genera una muestra puntual (`capture_sample`, invocado por `main()`)
ejecutando ambos modos una vez.

### Ejecutar

```bash
python3 -m ingesta.capturas.bluesky_menciones_madrid
```

Escribe la muestra en
`ingesta/capturas/samples/bluesky_menciones_madrid_sample.json`
(configurable con `--out`). No requiere ninguna variable de entorno de
credenciales.

### Variables de entorno

| Variable                     | Por defecto                       | Descripción                                                                 |
| ------------------------------ | ------------------------------------ | ------------------------------------------------------------------------------ |
| `BLUESKY_API_BASE_URL`        | `https://api.bsky.app`              | Host del AppView de Bluesky (ver nota sobre `public.api.bsky.app` arriba).     |
| `BLUESKY_LANG`                 | `es`                                 | Idioma (`lang`) usado en las búsquedas de la muestra.                         |
| `BLUESKY_LIMIT_PER_QUERY`      | `5`                                  | Nº máximo de posts por búsqueda individual (`limit` de la API).               |
| `BLUESKY_SAMPLE_PLACES`        | `Puerta del Sol\|Parque del Retiro\|Malasaña` | Lugares de ejemplo para el modo `search_place` (separados por `\|`).          |
| `BLUESKY_SAMPLE_DISTRICTS`     | 3 primeros de `DEFAULT_DISTRICTS`   | Distritos de ejemplo para `search_district_sweep` (separados por `\|`).       |
| `BLUESKY_EVENT_TERMS`          | 2 primeros de `DEFAULT_EVENT_TERMS` | Términos de eventos de ejemplo para `search_district_sweep` (separados por `\|`). |
| `HTTP_TIMEOUT_SECONDS`        | `15`                                  | Timeout por request HTTP.                                                      |
| `HTTP_MAX_RETRIES`            | `3`                                   | Reintentos ante fallo de red (backoff lineal simple).                          |
| `HTTP_RETRY_BACKOFF_SECONDS`  | `2`                                   | Base del backoff entre reintentos (segundos * intento).                        |
| `LOG_LEVEL`                   | `INFO`                                | Nivel de logging (también configurable con `--log-level`).                     |

Los valores por defecto de `BLUESKY_SAMPLE_DISTRICTS`/`BLUESKY_EVENT_TERMS`
se recortan a 3/2 elementos (de los 21 distritos y 6 términos completos que
sí usaría un barrido real) precisamente para que la muestra de esta tarea
sea pequeña; un futuro productor programado real pasaría la lista completa.

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "bluesky_menciones_madrid",
  "mode": "bajo_demanda",
  "match_term": "Puerta del Sol",
  "post_hash": "ab508899abd85c6d",
  "text": "📣No podemos seguir tolerando esta barbarie financiada...",
  "lang": "es",
  "created_at": "2026-08-13T11:26:39.707Z",
  "indexed_at": "2026-08-13T11:26:41.312Z",
  "like_count": 1,
  "repost_count": 0,
  "reply_count": 1,
  "quote_count": 0,
  "captured_at": "2026-08-13T17:16:57.338443+00:00"
}
```

- `mode`: `"bajo_demanda"` (de `search_place`) o `"distrito_sweep"` (de
  `search_district_sweep`) — un único dataset con ambos modos mezclados,
  igual que el patrón ya usado en `aforos_peatones_bicicletas_madrid.py`
  (tarea 013, campo `mode` análogo); quien solo necesite un modo filtra por
  este campo.
- `match_term`: el lugar/hashtag (`search_place`) o el distrito/término de
  evento con el prefijo `"eventos:"` (`search_district_sweep`) que produjo
  el resultado — no hay ninguna clasificación geográfica más fina que esto.
- `text`/`post_hash`: ver sección de privacidad arriba.
- `created_at`: fecha de creación del post según su propio registro AT
  Protocol (tal cual la publica Bluesky, con milisegundos y `Z`).
  `indexed_at`: cuándo lo indexó el AppView de Bluesky. `captured_at`:
  cuándo lo capturó este productor (UTC, ISO-8601).
- `like_count`/`repost_count`/`reply_count`/`quote_count`: contadores
  públicos del post en el momento de la captura.
- No hay `location`/coordenadas: Bluesky no da geolocalización de los
  posts; la "ubicación" de un registro es puramente textual (`match_term`).

### Nota sobre la captura real en esta sesión (tarea 016)

Se completó una **captura real en vivo** con ambos modos: el fixture
commiteado en
`ingesta/capturas/samples/bluesky_menciones_madrid_sample.json` son 40
posts reales (15 de `search_place` sobre "Puerta del Sol", "Parque del
Retiro" y "Malasaña"; 25 de `search_district_sweep` sobre los distritos
Centro/Arganzuela/Retiro y los términos de eventos "concierto"/"fiesta"),
descargados ejecutando el script tal cual contra `https://api.bsky.app`
durante esta sesión — no son datos de ejemplo generados a mano. El fixture
de test (`ingesta/tests/fixtures/bluesky_search_posts_sample.json`, usado
solo para probar `normalize_post` sin red) sí usa autores/`uri`/`cid`
inventados en vez de reales, a propósito: no hace falta preservar
identificadores reales de terceros en un fixture de test, y evita dejar en
el repositorio datos de personas reales vinculados a un texto concreto
(aunque `normalize_post` los descarte de todas formas al normalizar).

## `capturas/agenda_eventos_madrid.py` — Agenda de eventos culturales de Madrid (dos fuentes, muestra puntual)

Complementa a `bluesky_menciones_madrid.py` (tarea 016, opiniones/menciones
informales) con una fuente de mayor calidad para "eventos" en concreto: dato
oficial y programado (conciertos, exposiciones, actividades en
bibliotecas/centros culturales/juveniles/de mayores...), sin scraping ni
zona gris, a diferencia de la tarea 012 y de intentar inferir eventos solo
de redes sociales. Se investigaron y descartaron dos alternativas antes de
esta tarea: Eventbrite (su búsqueda pública de eventos está descontinuada,
la API solo gestiona eventos propios) y Foursquare (reseñas/tips detrás de
un tier de pago).

### Dos fuentes en un único dataset, con campo `source`

- **`agenda_eventos_madrid_municipal`**: dataset "Actividades culturales y
  de ocio municipal en los próximos 100 días" del portal de datos abiertos
  del Ayuntamiento de Madrid (id `206974-0-agenda-eventos-culturales-100`,
  licencia CC-BY 4.0). Cubre únicamente actividades en centros
  **municipales**.
- **`agenda_turismo_esmadrid`**: dataset "Agenda de la ciudad de Madrid" (id
  `300028-0-agenda-turismo`), gestionado por Madrid Destino (`esmadrid.com`,
  el portal de promoción turística de la ciudad). Se investigó, tal como
  pedía el enunciado de la tarea, si aportaba cobertura relevante que la
  agenda municipal no tiene: **sí** — conciertos y espectáculos en
  salas/teatros privados (verificado en vivo: p.ej. "Zucchero (Madrid Live
  Experience 2026)", "Real Madrid - Ajax Vrouwen (UEFA Women's Champions
  League)"), ferias, exposiciones y grandes eventos de ciudad que no se
  celebran en centros municipales. Por eso se decidió **incluirla en esta
  misma tarea**, no dejarla anotada para el futuro: el esfuerzo extra (un
  segundo `fetch_*`/`normalize_*` que parsea XML) fue moderado y el esquema
  normalizado absorbe ambas fuentes con los mismos campos.

Ambas se combinan en un único fichero de muestra con el campo `source` para
distinguirlas (mismo patrón que `mode` en `bluesky_menciones_madrid.py`,
tarea 016), no en dos ficheros separados: quien consuma la agenda para
responder "¿qué hay hoy en Malasaña?" quiere ambas fuentes juntas.

**Licencia de `agenda_turismo_esmadrid`**: `package_show` la marca como
`"isopen": false` (licencia `madrid-destino`, distinta de la CC-BY del
dataset municipal). Se leyó la licencia completa (consultada en vivo,
<https://datos.madrid.es/pages/condiciones-reutilizacion-informacion-madrid-destino>):
permite expresamente la reutilización de "documentos textuales y datos"
para fines comerciales y no comerciales, pero **limita la reutilización de
fotografías y material gráfico**. Por eso `normalize_esmadrid_event` no
incluye ninguna URL de imagen del bloque `<multimedia>` del XML de origen,
aunque el dato esté disponible — solo texto/geolocalización/fechas.

### Fuente elegida para cada dataset, y por qué

- **Municipal**: el endpoint CKAN `datastore_search`
  (`https://datos.madrid.es/api/action/datastore_search?resource_id=...`)
  que sugería el enunciado de la tarea **respondió con una página HTML de
  mantenimiento** ("Ayuntamiento de Madrid - En mantenimiento", verificado
  en vivo durante esta sesión) en vez de JSON. En su lugar se usa
  directamente el recurso JSON-LD del propio catálogo
  (`https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json`),
  que respondió con normalidad (669 eventos en el momento de la captura) y
  es, de hecho, más simple de consumir que CKAN: una lista `@graph` de
  objetos ya tipados, sin paginación que gestionar para una muestra pequeña.
- **esMadrid**: el dataset solo ofrece recursos XML (uno por idioma). Se usa
  el recurso en español (`https://www.esmadrid.com/opendata/agenda_v1_es.xml`).
  Este host **devuelve `403 Forbidden` (bloqueo de WAF) con el User-Agent
  por defecto de `requests`**, verificado en vivo durante esta sesión; con
  un User-Agent de navegador responde `200` con normalidad. El módulo envía
  un User-Agent de navegador en ambas peticiones (a `datos.madrid.es` y a
  `esmadrid.com`) por simplicidad, sin efecto adverso en el primero.

### Simplificación deliberada: solo el primer rango de fechas de esMadrid

El dato municipal ya viene con un único `dtstart`/`dtend` por evento. El de
esMadrid modela recurrencia real (`<fechas><rango>` con `inicio`/`fin`/
`dias`, más `<exclusion>`/`<inclusion>` para sesiones sueltas que se saltan
o añaden al patrón). Modelar esa recurrencia completa excede el alcance de
"esquema mínimo y consistente" de esta tarea: `normalize_esmadrid_event`
solo toma el `inicio`/`fin` del primer `<rango>` como `start_datetime`/
`end_datetime` (el periodo en que el evento está activo, sin desglosar cada
sesión concreta) y conserva el texto libre de `<item name="Horario">` en
`schedule_text`, para que quien lo necesite pueda leer el patrón exacto. Si
una tarea futura necesita fechas de sesión individuales exactas, debería
parsear ese texto o `dias`/`exclusion`/`inclusion` explícitamente.

### Ejecutar

```bash
python3 -m ingesta.capturas.agenda_eventos_madrid
```

Sin autenticación. Escribe la muestra combinada (por defecto 5 eventos de
cada fuente) en `ingesta/capturas/samples/agenda_eventos_madrid_sample.json`.

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `AGENDA_MADRID_MUNICIPAL_URL` | URL del recurso JSON-LD municipal | recurso oficial de datos.madrid.es |
| `AGENDA_MADRID_ESMADRID_URL` | URL del XML de esMadrid (español) | recurso oficial de esmadrid.com |
| `AGENDA_MADRID_MUNICIPAL_SAMPLE_SIZE` | Nº de eventos municipales en la muestra | `5` |
| `AGENDA_MADRID_ESMADRID_SAMPLE_SIZE` | Nº de eventos de esMadrid en la muestra | `5` |
| `AGENDA_MADRID_DESCRIPTION_MAX_LENGTH` | Longitud máxima de `description` (recorte con `...`) | `400` |
| `HTTP_TIMEOUT_SECONDS` | Timeout de cada petición HTTP | `30.0` |
| `HTTP_MAX_RETRIES` | Reintentos por petición | `3` |
| `HTTP_RETRY_BACKOFF_SECONDS` | Backoff lineal entre reintentos | `2.0` |

### Esquema normalizado (por registro, común a ambas fuentes)

```json
{
  "schema_version": 1,
  "source": "agenda_eventos_madrid_municipal",
  "event_id": "50369523",
  "title": "35 edición del Festival de Cine de Madrid",
  "description": "...",
  "category": "ProgramacionDestacadaAgendaCultura",
  "start_datetime": "2026-09-15T00:00:00",
  "end_datetime": "2026-09-20T23:59:00",
  "schedule_text": null,
  "free": false,
  "price_info": null,
  "location": {
    "venue_name": "Cineteca Madrid",
    "address": "PLAZA LEGAZPI 8",
    "district": "Arganzuela",
    "neighborhood": "Chopera",
    "postal_code": "28045",
    "lat": 40.39130985242181,
    "lon": -3.6958028442054074,
    "srid": "EPSG:4326"
  },
  "url": "http://www.madrid.es/...",
  "captured_at": "2026-08-13T22:18:01.293752+00:00"
}
```

- `source`: `"agenda_eventos_madrid_municipal"` o `"agenda_turismo_esmadrid"`.
- `category`: para el dataset municipal, el último segmento del `@type`
  (URI del vocabulario de datos.madrid.es, p.ej.
  `.../TeatroPerformance/ComediaMonologo` -> `"ComediaMonologo"`); para
  esMadrid, la ruta `"Tipo > Categoría > Subcategoría"` unida con `" > "`
  (p.ej. `"Eventos > Teatro y danza > Humor"`). `null` si la fuente no la da
  (ocurre en el dataset municipal, no todos los eventos tienen `@type`).
- `start_datetime`/`end_datetime`: ISO-8601 sin zona horaria (el dato de
  origen no la especifica). Para esMadrid, solo fecha (`"YYYY-MM-DD"`, sin
  hora) — el horario real va en `schedule_text` como texto libre.
- `free`: `true`/`false` para el dataset municipal (campo `free` de origen);
  siempre `null` para esMadrid, que no lo distingue de forma estructurada
  (solo texto libre en `price_info`).
- `location.district`/`location.neighborhood`: solo el dataset municipal los
  da (extraídos del último segmento de las URIs `address.district`/
  `address.area` del vocabulario administrativo de Madrid); siempre `null`
  para esMadrid.
- `location.srid`: `"EPSG:4326"` si hay coordenadas, `null` si no.

### Nota sobre la captura real en esta sesión (tarea 017)

Se completó una **captura real en vivo** de ambas fuentes: el fixture
commiteado en `ingesta/capturas/samples/agenda_eventos_madrid_sample.json`
son 10 eventos reales (5 de datos.madrid.es, 5 de esmadrid.com),
descargados ejecutando el script tal cual durante esta sesión — no son
datos de ejemplo generados a mano. Ambas fuentes respondieron con
normalidad una vez resuelto el bloqueo de WAF de esmadrid.com descrito
arriba; no hubo ningún problema de acceso persistente que documentar (a
diferencia de otras tareas de este proyecto con fuentes bloqueadas o sin
credenciales disponibles en este entorno).

## `capturas/aemet_prevision_avisos.py` — Previsión meteorológica y avisos de AEMET (muestra puntual, bloqueada)

Complementa a `meteorologia_madrid.py` (tarea 008, tiempo **actual**) con
**previsión** a varios días y **avisos oficiales** de fenómenos
meteorológicos adversos, la fuente oficial española para ambas cosas:
[AEMET OpenData](https://opendata.aemet.es). Dos funciones:

- `fetch_prediccion(config, municipio_code="28079")`: previsión diaria (7
  días) para el municipio dado (código INE; `28079` = Madrid capital).
- `fetch_avisos(config, area_code="72")`: avisos vigentes para el área dada
  (código CCAA de AEMET; `72` = "Madrid, Comunidad de").

### Bloqueo de registro: la API key exige resolver un reCAPTCHA

Se investigó en vivo, durante esta sesión, el formulario de alta de usuario
(<https://opendata.aemet.es/centrodedescargas/altaUsuario>): pide un email y,
antes de poder enviarlo, **obliga a resolver un reCAPTCHA de Google**
(comprobado leyendo el JS del propio formulario). No hay ninguna vía de alta
alternativa sin CAPTCHA. Es un bloqueo manual no automatizable en este
pipeline, de la misma naturaleza que el de la verificación de correo de la
EMT (tarea 003) y el de la cuenta de Google Cloud (tarea 012). Se verificó
también, sin key, que el servicio exige un `api_key` con forma de JWT
(`?api_key=test` → `401`, `"JWT strings must contain exactly 2 period
characters. Found: 0"`) — no existe ninguna clave de prueba pública.

El código queda completo y listo para ejecutarse tal cual el día que alguien
complete el alta manualmente y configure `AEMET_API_KEY` (nunca hardcodeada);
se verificó en vivo, con una clave con forma de JWT pero inválida, que la
petición llega correctamente construida hasta AEMET y falla solo por
autenticación (`401`), no por ningún error de este módulo. `main()` falla
explícitamente si la variable no está definida.

### El esquema sí se obtuvo, sin necesidad de una key válida

AEMET publica su especificación OpenAPI completa **sin autenticación** en
<https://opendata.aemet.es/AEMET_OpenData_specification.json> (verificado en
vivo). De ahí se tomaron los dos endpoints, sus parámetros (incluida la
tabla de códigos de área CCAA) y el envoltorio de respuesta en dos pasos que
usa toda la API de AEMET OpenData: la llamada con `api_key` no trae el dato,
trae `{"descripcion", "estado", "datos", "metadatos"}`, donde `datos` es la
URL real del payload.

El esquema del payload de previsión diaria (nombres de campo camelCase:
`probPrecipitacion`, `estadoCielo`, `viento`, `rachaMax`, `temperatura`,
`sensTermica`, `humedadRelativa`, `uvMax`...) se contrastó además con **datos
reales y en vivo** de Madrid capital, obtenidos sin ninguna autenticación del
feed público legado que la propia web de AEMET usa para pintar la ficha de
cada municipio
(`https://www.aemet.es/xml/municipios/localidad_28079.xml`, verificado en
vivo: `200 OK`, mismos campos que OpenData en `snake_case`/atributos XML,
codificación `ISO-8859-15`). Los valores numéricos de la muestra commiteada
son esos valores reales de esa consulta en vivo (Madrid, 13 de agosto de
2026), reestructurados a mano al esquema JSON documentado de OpenData.

**Quirk documentado:** el payload de `datos` de OpenData se sirve realmente
en `ISO-8859-15`, no en UTF-8, con independencia de la cabecera
`Content-Type`; `fetch_prediccion_raw` decodifica explícitamente con ese
códec.

Solo se implementa la previsión **diaria**, no la horaria: comparten el
envoltorio de dos pasos, pero el payload horario tiene una forma distinta
que no se ha podido contrastar con datos reales en esta sesión (no hay un
feed legado sin key equivalente para horaria — las URLs candidatas
devuelven `404`, verificado en vivo). Se prefiere dejarla fuera antes que
una implementación sin verificar.

El esquema de avisos (documentos CAP 1.2 dentro de un `.tar.gz`) sigue el
estándar CAP y el patrón documentado por la propia
[página de ayuda de AEMET](https://www.aemet.es/es/eltiempo/prediccion/avisos/ayuda)
(niveles amarillo/naranja/rojo, parámetros `AEMET-Meteoalerta
nivel`/`fenomeno`/`zona`), pero **no se ha podido contrastar contra un
documento CAP real** (no se ha encontrado un feed público equivalente sin
key) — menor confianza que la previsión diaria, explícita aquí y en el
docstring del módulo.

### Ejecutar

```bash
export AEMET_API_KEY=...  # ver "Bloqueo de registro" arriba
python3 -m ingesta.capturas.aemet_prevision_avisos
```

Escribe dos muestras: `ingesta/capturas/samples/aemet_prevision_madrid_sample.json`
(previsión, todos los días que traiga la fuente) y
`ingesta/capturas/samples/aemet_avisos_madrid_sample.json` (avisos vigentes,
puede quedar vacía sin error si no hay ninguno).

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `AEMET_API_KEY` | API key de AEMET OpenData (obligatoria) | *(vacío)* |
| `AEMET_MUNICIPIO_CODE` | Código INE de municipio para la previsión | `28079` (Madrid capital) |
| `AEMET_AREA_CODE` | Código de área CCAA de AEMET para los avisos | `72` (Madrid) |
| `AEMET_PREDICCION_URL_TEMPLATE` | Plantilla de URL del endpoint de previsión diaria | recurso oficial de OpenData |
| `AEMET_AVISOS_URL_TEMPLATE` | Plantilla de URL del endpoint de avisos | recurso oficial de OpenData |
| `HTTP_TIMEOUT_SECONDS` | Timeout de cada petición HTTP | `15.0` |
| `HTTP_MAX_RETRIES` | Reintentos por petición (no se reintenta un `429` de cuota) | `3` |
| `HTTP_RETRY_BACKOFF_SECONDS` | Backoff lineal entre reintentos | `2.0` |

### Límite de cuota del tier gratuito

AEMET OpenData es un tier gratuito con límite de peticiones (la propia
especificación documenta una respuesta `429`, *"petición que sobrepasa los
límites del servicio"*, para ambos endpoints). Este módulo, a propósito, no
reintenta un `429` (`_get_with_retries` lo detecta y falla explícitamente en
vez de agotar reintentos contra un límite que no se va a levantar
reintentando). No se ha podido determinar el número exacto de peticiones
permitidas por día/minuto sin una key real con la que probarlo; queda como
nota para quien complete el alta.

### Esquema normalizado: previsión (por día)

```json
{
  "schema_version": 1,
  "source": "aemet_prediccion_municipio",
  "municipio_code": "28079",
  "municipio_name": "Madrid",
  "province": "Madrid",
  "elaborated_at": "2026-08-13T21:19:10",
  "valid_date": "2026-08-15",
  "sky_state": "Intervalos nubosos con lluvia",
  "sky_state_code": "23",
  "precipitation_probability_pct": "95",
  "temperature_max_c": 34,
  "temperature_min_c": 22,
  "thermal_sensation_max_c": 31,
  "thermal_sensation_min_c": 21,
  "humidity_max_pct": 65,
  "humidity_min_pct": 25,
  "wind_direction": "SE",
  "wind_speed_kmh": "20",
  "wind_gust_max_kmh": "40",
  "uv_max": 8,
  "captured_at": "2026-08-13T22:32:05.022443+00:00",
  "is_mock": true
}
```

- Cada registro es el resumen del **día completo** (periodo `"00-24"`) de
  una de las magnitudes que AEMET repite por sub-periodo (mañana/tarde,
  franjas de 6h); no se desglosan los sub-periodos en el esquema
  normalizado. `temperature_*`/`thermal_sensation_*`/`humidity_*` sí son
  directamente el máximo/mínimo del día que da la fuente (no están
  troceados por periodo).
- `wind_gust_max_kmh` puede ser `null`: no todos los días traen racha
  máxima para el periodo `"00-24"` (ocurre incluso en datos reales, ver
  fixture de test).
- Los tipos siguen tal cual a la fuente (algunos campos numéricos vienen
  como string en el JSON real de AEMET, p.ej. `precipitation_probability_pct`/
  `wind_speed_kmh`; no se fuerza su conversión a número para no enmascarar
  el dato tal como lo publica AEMET).
- `is_mock: true` en la muestra commiteada (ver "Bloqueo de registro").

### Esquema normalizado: avisos

```json
{
  "schema_version": 1,
  "source": "aemet_avisos_cap",
  "identifier": "es-aemet-CAP-2026-08-14-00-72-01",
  "sent_at": "2026-08-14T07:45:00+02:00",
  "zone": "Madrid",
  "level": "amarillo",
  "phenomenon": "Altas temperaturas",
  "probability": "100%",
  "severity": "Moderate",
  "urgency": "Expected",
  "certainty": "Likely",
  "effective_from": "2026-08-14T13:00:00+02:00",
  "effective_until": "2026-08-14T21:00:00+02:00",
  "headline": "Aviso amarillo por altas temperaturas en Madrid",
  "description": "Temperaturas máximas en torno a 38-39 grados en la Comunidad de Madrid.",
  "captured_at": "2026-08-13T22:32:05.022443+00:00",
  "is_mock": true
}
```

- `level`: `"amarillo"` / `"naranja"` / `"rojo"` (ver significado de cada
  uno más abajo, en "Cadencia real de publicación").
- `effective_from`/`effective_until`: ámbito temporal del aviso (`onset`/
  `expires` del documento CAP de origen).
- Solo se conservan los bloques en español (`language` empieza por `"es"`)
  cuando un mismo aviso trae varios idiomas.
- Una lista vacía (sin error) es el resultado normal cuando no hay ningún
  aviso vigente para el área en el momento de la captura.

### Cadencia real de publicación (investigada en vivo)

- **Previsión diaria**: la propia especificación OpenAPI la documenta como
  *"Periodicidad de actualización: continuamente"* — no hay un número fijo
  de veces al día, AEMET la recalcula y publica de forma continua según van
  llegando nuevos modelos/observaciones. Para un scheduling real, sondear
  cada 1-3 horas sería más que suficiente sin sobrecargar el servicio ni
  perderse actualizaciones relevantes para "¿voy esta noche?".
- **Avisos**: la [página de ayuda de AEMET](https://www.aemet.es/es/eltiempo/prediccion/avisos/ayuda)
  documenta explícitamente los periodos preferentes de emisión (hora
  peninsular): **07:30-09:00** (avisos para hoy, D), **10:30-11:30**
  (avisos para D+1 y D+2), **17:00-19:00** (revisión de todos los avisos) y
  **23:50** (avance para D+3). Fuera de esos huecos solo se emiten avisos
  si hay un cambio significativo que lo justifique. Un scheduling real
  debería sondear en esos 4 momentos, no en un intervalo fijo arbitrario.
- Niveles de aviso (misma página): **amarillo** (peligro bajo, "esté
  atento"), **naranja** (peligro importante, "esté preparado"), **rojo**
  (peligro extraordinario, "actúe" según indicaciones de las autoridades).

### Nota sobre la captura real en esta sesión (tarea 018)

No se pudo completar una captura real en vivo contra la API de AEMET
OpenData: el registro de la API key está bloqueado (ver "Bloqueo de
registro"). Se verificó en vivo, con una clave con forma de JWT pero
inválida, que ambos endpoints (`/prediccion/especifica/municipio/diaria/28079`
y `/avisos_cap/ultimoelaborado/area/72`) responden `401` de forma esperada
(la petición llega bien construida hasta AEMET). Las muestras commiteadas en
`ingesta/capturas/samples/aemet_prevision_madrid_sample.json` y
`aemet_avisos_madrid_sample.json` se generaron a mano ejecutando las propias
funciones `normalize_prediccion_dia`/`normalize_aviso` de este módulo sobre
datos de ejemplo (los de previsión, con valores reales de Madrid capturados
en vivo del feed legado sin key; los de avisos, un único escenario
verosímil pero inventado, dado que no hay forma de saber si hay algún aviso
realmente vigente sin la key), con `"is_mock": true` en cada registro.

## `capturas/cams_calidad_aire_madrid.py` — Previsión de calidad del aire de Copernicus CAMS (muestra puntual, bloqueada)

Complementa a `calidad_aire_madrid.py` (tarea 006, mediciones **en tiempo
real** de la red municipal, solo Madrid) con una **previsión** horaria a 4
días vista, validada contra observaciones oficiales a escala europea:
[Copernicus Atmosphere Monitoring Service (CAMS)](https://ads.atmosphere.copernicus.eu/datasets/cams-europe-air-quality-forecasts),
dataset `cams-europe-air-quality-forecasts` del Atmosphere Data Store (ADS).
Una única función: `fetch_forecast(config, run_date=None)` descarga y
normaliza la previsión de NO2/O3/PM2.5/PM10 para un recorte geográfico
pequeño alrededor de Madrid capital.

### Bloqueo de registro: cuenta real ligada a identidad, no un CAPTCHA

A diferencia de AEMET (tarea 018) o la EMT (tarea 003), el formulario de
alta de la ADS API (`accounts.ecmwf.int/.../registrations?client_id=cds...`,
investigado en vivo durante esta sesión) **no tiene reCAPTCHA ni ningún
otro CAPTCHA**: solo pide nombre, apellidos, email, contraseña y su
confirmación. Aun así se trata como el mismo tipo de bloqueo que en esas
tareas: completar el alta implica **crear una cuenta real, persistente y
ligada a la identidad de quien la crea** en un servicio de terceros, con
una contraseña elegida en el momento y, muy probablemente, una confirmación
por email (patrón estándar del sistema de identidad que usa
`accounts.ecmwf.int`, Keycloak/EU Login) — un paso para el que esta sesión
no tiene acceso a ningún buzón de correo. Elegir una contraseña y registrar
una cuenta a nombre de un tercero sin que haya un humano confirmando esa
acción en el momento no es algo que este pipeline autónomo deba hacer por
iniciativa propia. El código queda completo y listo para ejecutarse tal
cual el día que alguien complete el alta manualmente y configure
`CAMS_ADS_API_KEY` (nunca hardcodeada); `capture_sample`/`main()` fallan
explícitamente si la variable no está definida.

La [página oficial "How to use the CDS/ADS API"](https://ads.atmosphere.copernicus.eu/how-to-api)
(consultada en vivo) confirma además que, antes de poder descargar
`cams-europe-air-quality-forecasts`, hay que aceptar sus "Terms of Use"
desde su página en el ADS con la cuenta ya logueada — otro paso manual
explícitamente no automatizable, documentado también ahí.

### Autenticación real: un "personal access token", no una API key clásica

El token de acceso personal se obtiene del perfil del usuario tras el alta
y se usa junto con la URL base del servicio
(`https://ads.atmosphere.copernicus.eu/api`); el cliente oficial `cdsapi`
normalmente los lee de `$HOME/.cdsapirc`. Este módulo, para no depender de
un fichero fuera del repositorio y seguir la norma del proyecto de
"credenciales por variable de entorno", construye
`cdsapi.Client(url=CAMS_ADS_URL, key=CAMS_ADS_API_KEY)` explícitamente, sin
tocar `~/.cdsapirc`.

### El esquema de la petición y de los datos sí se obtuvo, sin necesidad de un token válido

El ADS expone públicamente, sin autenticación, la descripción del proceso
de cada dataset
(`GET /api/retrieve/v1/processes/cams-europe-air-quality-forecasts`,
verificado en vivo: `200 OK`). De ahí salen, con certeza, todos los
parámetros válidos de la petición: contaminante (`variable`), modelo
(`model`), nivel vertical (`level`), tipo (`type`), hora de previsión
(`leadtime_hour`), formato de salida (`data_format`, por defecto real
`"netcdf_zip"` — un `.zip` con uno o varios `.nc` dentro, no un `.nc`
suelto) y recorte geográfico (`area`, `[norte, oeste, sur, este]`).

**Contaminantes validados (restricción explícita de esta tarea):** la
documentación pública del dataset confirma que solo NO, NO2, SO2, O3, PM2.5,
PM10 y polvo se validan regularmente contra observaciones in situ; el resto
(polen, COVs, amoniaco...) se declara explícitamente "experimental, sin
validar". `POLLUTANT_VARIABLES` solo incluye esos 7.

Los nombres cortos de variable **dentro** de cada NetCDF (distintos del
nombre de la petición ADS, p.ej. `nitrogen_dioxide` en la petición frente a
`no2_conc` dentro del fichero) se contrastaron con varias fuentes públicas
que citan explícitamente `no2_conc`/`o3_conc`/`pm10_conc`/`pm2p5_conc`/
`so2_conc` para este mismo dataset. Para `nitrogen_monoxide`/`dust` no se
encontró ninguna fuente que citara su nombre corto exacto: se mapean como
`no_conc`/`dust_conc` por el mismo patrón que las cinco anteriores, pero
**sin poder contrastarlo contra un fichero real** (mismo tipo de aviso de
menor confianza que el esquema de avisos CAP de la tarea 018).
`normalize_forecast_file` es indiferente a qué subconjunto de
`POLLUTANT_VARIABLES` esté realmente presente en un fichero: solo procesa
las que encuentra, así que un nombre equivocado no rompe la captura, solo
deja sin registros a ese contaminante.

### Área geográfica: un recorte pequeño alrededor de Madrid

El dataset cubre toda Europa (25°O-45°E, 30°N-72°N) a 0.1°×0.1°. El
parámetro `area` de la propia API permite recortar la petición en origen:
`DEFAULT_AREA` es una caja estrecha alrededor de Madrid capital, y
`normalize_forecast_file` se queda con el punto de rejilla más cercano al
centro de Madrid (40.4168, -3.7038) dentro de ese recorte.

### Ejecutar

```bash
export CAMS_ADS_API_KEY=...  # ver "Bloqueo de registro" arriba
python3 -m ingesta.capturas.cams_calidad_aire_madrid
```

Escribe una única muestra:
`ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json`.

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `CAMS_ADS_API_KEY` | Personal access token de la ADS API (obligatoria) | *(vacío)* |
| `CAMS_ADS_URL` | URL base de la ADS API | `https://ads.atmosphere.copernicus.eu/api` |
| `CAMS_POLLUTANTS` | Contaminantes a pedir, separados por comas (deben estar en `POLLUTANT_VARIABLES`) | `nitrogen_dioxide,ozone,particulate_matter_2.5um,particulate_matter_10um` |
| `CAMS_AREA` | Recorte geográfico `norte,oeste,sur,este`, separado por comas | caja alrededor de Madrid |
| `CAMS_MODEL` | Modelo/ensemble a pedir | `ensemble` |
| `CAMS_LEVEL` | Nivel vertical (`"0"` = superficie) | `0` |
| `CAMS_LEADTIME_HOURS` | Horas de previsión a pedir, separadas por comas | `0,1,2,3` |
| `CAMS_RUN_TIME` | Hora de la corrida a pedir (CAMS solo publica la de `00:00` UTC) | `00:00` |

### Por qué el modelo `ensemble` y no un modelo individual

CAMS combina la salida de once sistemas de previsión europeos en una
mediana de conjunto (`ensemble`), que la propia documentación señala como
de mejor rendimiento que cualquier modelo individual y además da una
estimación de incertidumbre por la dispersión entre modelos. Por eso es el
valor por defecto de `CAMS_MODEL`; `_build_request` admite pedir cualquiera
de los once modelos individuales (`chimere`, `dehm`, `emep`...) vía esa
misma variable si una tarea futura lo necesitara.

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "cams",
  "pollutant": "O3",
  "pollutant_code": "ozone",
  "value": 112.5,
  "unit": "µg m-3",
  "valid_datetime": "2026-08-13T12:00:00+00:00",
  "forecast_issued_at": "2026-08-13T00:00:00+00:00",
  "leadtime_hour": 12,
  "model": "ensemble",
  "latitude": 40.4,
  "longitude": -3.7,
  "captured_at": "2026-08-13T09:00:00+00:00",
  "is_mock": true
}
```

- `pollutant`/`pollutant_code`: etiqueta corta legible (`"O3"`) y nombre de
  variable de la petición ADS (`"ozone"`).
- `valid_datetime`: instante al que corresponde la previsión (`forecast_issued_at`
  + `leadtime_hour` horas).
- `forecast_issued_at`: instante de la corrida que generó la previsión
  (siempre `00:00` UTC del día de la corrida — CAMS solo publica una
  corrida diaria, ver cadencia más abajo).
- `latitude`/`longitude`: coordenadas reales del punto de rejilla de 0.1°
  más cercano al centro de Madrid dentro del `area` pedido (no
  necesariamente 40.4168/-3.7038 exactos).
- `is_mock: true` en la muestra commiteada (ver "Bloqueo de registro").

### Cadencia real de publicación (investigada en vivo, confirma "una vez al día" con matiz)

La documentación pública del dataset confirma **una única corrida diaria**
(`type=forecast`), a partir de las 00:00 UTC, publicada en **dos tandas**:
horas de previsión 0-48 disponibles a partir de las **06:45 UTC**, y horas
49-96 a partir de las **08:30 UTC**. "Una vez al día" es correcto como
resumen, pero conviene precisar que la previsión completa (hasta 96h) no
está íntegra hasta la segunda tanda del mismo día. Un scheduling real
debería sondear una vez tras cada tanda (p.ej. 07:00 y 09:00 UTC), no en un
intervalo arbitrario.

### Nota sobre la captura real en esta sesión (tarea 019)

No se pudo completar una captura real contra la ADS API: el registro de la
cuenta está bloqueado (ver "Bloqueo de registro" arriba). La muestra
commiteada en `ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json`
se generó a mano, siguiendo el esquema real documentado arriba, con valores
verosímiles para Madrid en un día de agosto (NO2 con pico de mañana, O3 con
pico de tarde propio de una ola de calor, PM2.5/PM10 moderados), marcada
`"is_mock": true` en cada registro. El test de flujo completo
(`FetchForecastTests` en `ingesta/tests/test_cams_calidad_aire_madrid.py`)
sí ejercita `fetch_forecast` de principio a fin (construcción de la
petición, descarga vía `cdsapi.Client.retrieve`, descompresión del `.zip`,
parseo del NetCDF y normalización) sustituyendo `cdsapi.Client` por un
doble que sirve un NetCDF sintético con la estructura real del dataset
(`ingesta/tests/fixtures/cams_forecast_sample.nc`), en vez de solo probar la
normalización de forma aislada.

## `capturas/calendario_laboral_madrid.py` — Calendario laboral y festivos de Madrid (muestra, carga puntual de referencia)

Décimo productor de carga puntual de referencia (tras `callejero_madrid.py`,
tarea 009; `barrios_distritos_madrid.py`, tarea 010; y `poi_madrid.py`, tarea
011): el calendario laboral de Madrid apenas cambia (el Ayuntamiento lo
publica de una vez con años completos de antelación), así que este módulo
**no tiene modo `--interval-seconds` ni bucle**, igual que esas tres. No es
una serie temporal ni necesita scheduling frecuente ni siquiera en
producción.

### Fuente elegida y por qué

Dataset "Calendario laboral" (id `300082-0-calendario_laboral`) de
[datos.madrid.es](https://datos.madrid.es/egob/catalogo/300082-0-calendario_laboral),
recurso **CSV**
(`.../resource/300082-1-calendario_laboral-csv/download/300082-1-calendario_laboral-csv.csv`).
El dataset también publica ICS y XLS/PDF; se descartó el ICS porque solo
lista los días **festivos** de un único año (verificado en vivo: 14 eventos
para 2025), sin el resto del calendario (laborable/sábado/domingo) que pide
esta tarea. El CSV, en cambio, trae **un registro por cada día natural desde
el 01/01/2013 hasta el 31/12/2026** (5.112 filas, verificado en vivo), con
la clasificación de jornada y, en los días festivos, su tipo y nombre.
Accesible **sin ninguna autenticación ni API key**.

### Dos problemas de calidad de datos de la propia fuente (documentados, no corregidos)

Detectados en vivo recorriendo las 5.112 filas reales del CSV:

1. **Falta el 29/02/2016**: 2016 fue bisiesto, pero el CSV salta del
   28/02/2016 al 01/03/2016 (el único hueco en toda la serie 2013-2026, por
   lo demás contigua día a día). No se rellena con un valor inventado.
2. **Dos días marcados `festivo` con `Tipo de Festivo` vacío**
   (`15/05/2016` y `02/05/2023`): `normalize_day_record` deja
   `holiday_type`/`holiday_type_raw` a `None` en esos casos en vez de
   inferir un valor.

### Ejecutar

```bash
python3 -m ingesta.capturas.calendario_laboral_madrid
```

Sin autenticación. Descarga el CSV completo (2013-2026), lo normaliza
entero y escribe solo el año más reciente disponible (o
`MADRID_CALENDAR_SAMPLE_YEAR` si se fija) en
`ingesta/capturas/samples/calendario_laboral_madrid_sample.json`.

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `MADRID_CALENDAR_CSV_URL` | URL del recurso CSV | recurso oficial de datos.madrid.es |
| `MADRID_CALENDAR_SAMPLE_YEAR` | Año a incluir en la muestra | año más reciente presente en el CSV |
| `HTTP_TIMEOUT_SECONDS` | Timeout de la petición HTTP | `30.0` |
| `HTTP_MAX_RETRIES` | Reintentos de la petición | `3` |
| `HTTP_RETRY_BACKOFF_SECONDS` | Backoff lineal entre reintentos | `2.0` |

### Esquema normalizado (por registro, un registro = un día natural)

```json
{
  "schema_version": 1,
  "source": "madrid_calendario_laboral",
  "date": "2026-01-01",
  "weekday": "jueves",
  "day_type": "festivo",
  "is_holiday": true,
  "holiday_type": "nacional",
  "holiday_type_raw": "Festivo nacional",
  "holiday_name": "Año Nuevo",
  "ingested_at": "2026-08-13T22:56:10.507314+00:00"
}
```

- `day_type`: `"laborable"` / `"festivo"` / `"sabado"` / `"domingo"`, tal
  cual clasifica la fuente (los sábados y domingos no festivos no se marcan
  `"laborable"`).
- `is_holiday`: derivado (`day_type == "festivo"`) — el campo pensado para
  que el modelo de afluencia trate un día festivo entre semana como un
  domingo sin tener que interpretar `day_type` cada vez.
- `holiday_type`: ámbito del festivo normalizado a `"nacional"` /
  `"regional"` / `"local"` (mapeado desde `holiday_type_raw` vía
  `HOLIDAY_TYPE_MAP`); `null` si el día no es festivo o si la fuente no trae
  tipo (ver "Dos problemas de calidad de datos" arriba).
- `holiday_type_raw`: texto original de la columna `Tipo de Festivo` de la
  fuente (p.ej. distingue un "Traslado de la fiesta de la Comunidad de
  Madrid" del festivo regional original, ambos mapeados a `"regional"` en
  `holiday_type`); `null` en las mismas condiciones que `holiday_type`.
- `holiday_name`: nombre del festivo (columna `Festividad`); `null` si no es
  festivo, o si lo es pero la fuente no trae nombre (ocurre en algún
  traslado, ver módulo).

### Muestra: un único año completo (2026), no todo 2013-2026

El dataset entero no es grande (5.112 filas, ~150 KB), pero se optó por
commitear solo **un año natural completo** (2026, el más reciente
disponible en el momento de esta captura — 365 días, con festivos de los
tres ámbitos: nacional, regional y local) en vez del histórico 2013-2026
completo: un año ya demuestra el esquema y cubre un ciclo completo de
laborables/fines de semana/festivos, y es más legible como fixture que un
JSON de 5.112 registros. Si una tarea futura necesita el histórico completo
para el modelo (p.ej. para entrenar con años pasados), la carga real hacia
S3/lakehouse no tiene ese límite — es una decisión solo del tamaño de la
*muestra* commiteada, no de lo que la fuente ofrece.

### Nota sobre la captura real en esta sesión (tarea 020)

Se completó una **captura real en vivo**: la muestra commiteada en
`ingesta/capturas/samples/calendario_laboral_madrid_sample.json` son los 365
días reales de 2026, descargados ejecutando
`python3 -m ingesta.capturas.calendario_laboral_madrid` tal cual contra el
CSV público durante esta sesión — no son datos de ejemplo generados a mano.
No hubo ningún bloqueo de acceso que documentar.

## `capturas/crtm_red_transporte_madrid.py` — Red estructural de transporte de Madrid (GTFS, CRTM; carga batch puntual, referencia)

Descarga los feeds GTFS estáticos que publica el Consorcio Regional de
Transportes de Madrid (CRTM) y los normaliza a un esquema mínimo de
**líneas con las paradas de un viaje representativo** (no el grafo
completo de horarios). Es contexto estructural de red (qué líneas existen,
por dónde pasan) — no llegadas en vivo: eso sigue bloqueado en la tarea
003 (EMT, registro con email sin verificar) y no se ha encontrado ninguna
alternativa abierta (ver "GTFS-RT" más abajo).

### Esto es una carga puntual de referencia, no una captura periódica

Igual que `callejero_madrid.py` (tarea 009), `barrios_distritos_madrid.py`
(tarea 010), `poi_madrid.py` (tarea 011) y `calendario_laboral_madrid.py`
(tarea 020), la red de líneas y paradas es un dato de **referencia**: CRTM
publica "cambios de servicio" unas pocas veces al año, no minuto a minuto.
Este módulo, a propósito, no tiene modo `--interval-seconds` ni bucle.

### Fuente elegida y por qué

Portal de datos abiertos del CRTM (`datos.crtm.es`, un sitio ArcGIS Hub).
Su buscador web (`/search`) es una SPA que no devuelve resultados por HTTP
directo; el catálogo completo sí es accesible sin autenticación a través
del feed DCAT-US 1.1 que expone todo portal ArcGIS Hub
(`https://datos.crtm.es/api/feed/dcat-us/1.1.json`, ~700 KB). Filtrando ese
catálogo por "gtfs" aparecen **6 feeds GTFS estáticos**, uno por
red/operador:

| `mode` (este módulo) | Red                                              | Tamaño del ZIP | ¿En la muestra? |
|-----------------------|--------------------------------------------------|----------------|------------------|
| `metro`               | Metro de Madrid                                  | 1.5 MB         | Sí |
| `emt`                  | Autobuses urbanos EMT Madrid                     | 18 MB          | Sí |
| `metro_ligero`         | Metro Ligero / Tranvía                           | 0.4 MB         | Sí |
| `cercanias`            | Cercanías Renfe (ámbito CRTM)                    | 6 KB           | Sí |
| `urbano_cm`            | Autobuses urbanos de la Comunidad de Madrid      | 8 MB           | No (soportado) |
| `interurbano_cm`       | Autobuses interurbanos de la Comunidad de Madrid | 72 MB          | No (soportado) |

Cada item se descarga sin autenticación desde el endpoint estándar de
contenido de ArcGIS Online
`https://www.arcgis.com/sharing/rest/content/items/{item_id}/data`
(verificado en vivo para los 6 feeds; es el mismo endpoint que usa el botón
"Download" de la página de cada dataset en `datos.crtm.es`). `MODE_FEEDS`
mapea cada `mode` a su `item_id`.

`DEFAULT_MODES` incluye `metro`, `emt` y `metro_ligero` (los tres que pedía
investigar explícitamente el enunciado de esta tarea) más `cercanias` (por
el hallazgo de calidad de datos que se documenta abajo). Se excluyen de la
muestra por defecto, aunque quedan soportados vía `CRTM_GTFS_MODES`,
`urbano_cm` e `interurbano_cm`: cubren la red de autobuses de la
**Comunidad de Madrid** (municipios fuera de la capital), no la red
estructural de la ciudad de Madrid que es el objeto de esta tarea, y el
segundo es, con diferencia, el feed más pesado del catálogo (72 MB) sin
aportar variedad de esquema sobre `emt`.

### GTFS-RT: no existe abierto (hallazgo relevante para la tarea 003)

Se ha buscado explícitamente, en vivo, un feed GTFS-RT (alertas de
servicio, posición de vehículos, retrasos) del CRTM, sin encontrar ninguno
accesible sin cuenta:

- El catálogo DCAT completo del portal solo contiene los 6 GTFS estáticos
  de la tabla anterior; una búsqueda por `gtfs-rt`, `tiempo real`,
  `realtime`, `alertas`, `incidencias`, `protobuf`, `vehicle`,
  `trip update` en el buscador del propio portal
  (`/api/search/v1/collections/dataset/items?q=...`) no devuelve ningún
  resultado adicional — ni en `datos.crtm.es` ni en su portal hermano
  `datos-movilidad.crtm.es` ("Portal de movilidad multimodal" del propio
  CRTM).
- [Transitland](https://www.transit.land/feeds/f-ezjm-consorcioregionaldetransportesdemadrid),
  el catálogo independiente de feeds GTFS/GTFS-RT más usado a nivel
  mundial, solo tiene registrado el feed GTFS estático de CRTM (23
  versiones históricas archivadas desde 2017); no hay feed GTFS-RT
  asociado.
- No existe un host `api.crtm.es` ni `opendata.crtm.es` accesible (fallo de
  conexión TLS en ambos, verificado en vivo).

**Conclusión**: CRTM no publica alertas/incidencias/retrasos en tiempo real
de forma abierta a nivel de toda la red multimodal, así que sigue sin haber
una alternativa multimodal a la API MobilityLabs de la EMT
(`transporte_publico_madrid.py`) para llegadas en vivo — es un hallazgo
negativo que queda documentado para no repetir esta misma búsqueda en el
futuro. *(Nota añadida en la tarea 024: la EMT se desbloqueó después por otra
vía — la tarea 003 había asumido incorrectamente que el login requería una
cuenta personal con email verificado; el mecanismo real es un login v1.1
con credenciales de aplicación `x-ClientId`/`passKey`, sin registro de
usuario. Ver la sección de `transporte_publico_madrid.py` más arriba.)*

### Formato real encontrado

Los 6 feeds son GTFS estándar (`agency.txt`, `routes.txt`, `stops.txt`,
`trips.txt`, `stop_times.txt`, `calendar(_dates).txt`, `shapes.txt`,
`frequencies.txt`, `fare_attributes.txt`, `fare_rules.txt`, `feed_info.txt`),
con `route_type` según la especificación GTFS (`0`=tranvía, `1`=metro,
`2`=cercanías/tren, `3`=autobús — los cuatro valores presentes en los
modos de la muestra). `stops.txt` incluye, junto a las paradas reales
(`location_type` vacío o `"0"`), elementos de accesibilidad con prefijo
`acc_` en el `stop_id` (ascensores, accesos de superficie...,
`location_type="2"`) que este módulo filtra al construir las paradas de
cada línea.

**Dos hallazgos de calidad de datos, documentados y no corregidos:**

1. El feed de `cercanias` publica `routes.txt` y `stops.txt` completos (las
   10 líneas de Cercanías con sus estaciones), pero `trips.txt` y
   `stop_times.txt` están **vacíos** (solo la cabecera, verificado en
   vivo) — CRTM no modela el servicio programado de Cercanías en su GTFS
   (es Renfe quien opera esa red). Por eso las líneas de `cercanias` en la
   muestra tienen `"stops": []`.
2. Dentro de `metro`, la línea 3 (`route_id="4__3___"`, incluida en la
   muestra por ser una de las primeras del fichero) tampoco tiene ningún
   `trip_id` en `trips.txt`, a diferencia de las líneas 1, 2, 4-12 y R del
   mismo feed — otro hueco real de la fuente. También aparece con
   `"stops": []` en la muestra commiteada.

### Esquema mínimo elegido: líneas con su secuencia de paradas de un viaje representativo

No hace falta modelar el grafo completo de horarios (calendarios,
frecuencias, todos los viajes). Para cada línea de muestra se elige un
único `trip_id` representativo (el primero con `direction_id="0"`, o el
primero disponible si no hay ninguno en ese sentido) y se usa su
`stop_times.txt` para obtener la secuencia ordenada real de paradas de esa
línea en ese sentido. `stop_times.txt` es, con diferencia, el fichero más
grande de un GTFS (84 MB sin comprimir en el feed de `emt` usado en esta
captura): se recorre en **streaming** directamente desde el ZIP,
descartando cada fila que no pertenezca a uno de los pocos `trip_id` de la
muestra, sin cargarlo entero en memoria ni escribirlo a disco — igual
criterio que "no leer el fichero completo en el contexto de la sesión" que
ya aplicaron `callejero_madrid.py`/`barrios_distritos_madrid.py` con sus
CSV completos.

### Un único dataset con campo `mode`, no un fichero por red

Sigue el patrón ya establecido en las tareas 013, 016 y 017: la muestra
combina los modos de `DEFAULT_MODES` en
`crtm_red_transporte_madrid_sample.json` con un campo `mode` que distingue
la red de origen de cada línea.

### Ejecutar

```bash
python3 -m ingesta.capturas.crtm_red_transporte_madrid
```

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `CRTM_GTFS_MODES` | Lista de modos a capturar, separados por comas (claves de `MODE_FEEDS`: `metro`, `emt`, `metro_ligero`, `cercanias`, `urbano_cm`, `interurbano_cm`) | `metro,emt,metro_ligero,cercanias` |
| `CRTM_GTFS_ROUTES_PER_MODE` | Líneas de muestra a normalizar por cada modo | `3` |
| `HTTP_TIMEOUT_SECONDS` | Timeout de las peticiones HTTP | `60.0` |
| `HTTP_MAX_RETRIES` | Reintentos ante fallo de red | `3` |
| `HTTP_RETRY_BACKOFF_SECONDS` | Backoff lineal entre reintentos | `2.0` |

### Esquema normalizado (por línea)

```json
{
  "schema_version": 1,
  "source": "crtm_red_transporte",
  "mode": "metro",
  "route_id": "4__1___",
  "short_name": "1",
  "long_name": "Pinar de Chamartín-Valdecarros",
  "route_type": "metro",
  "color": "2DBEF0",
  "url": "https://www.crtm.es/4__1___.aspx",
  "ingested_at": "2026-08-14T03:46:26.613022+00:00",
  "stops": [
    {
      "stop_id": "par_4_263",
      "name": "PINAR DE CHAMARTIN",
      "sequence": 0,
      "location": {"lat": 40.48014, "lon": -3.6668, "srid": "EPSG:4326"}
    }
  ]
}
```

- `mode`: red de origen (`metro`/`emt`/`metro_ligero`/`cercanias` en la
  muestra por defecto).
- `route_id`/`short_name`/`long_name`: identificador GTFS, número/código
  corto de línea, y descripción origen-destino, tal cual la fuente.
- `route_type`: etiqueta legible del `route_type` GTFS (`tranvia`, `metro`,
  `cercanias`, `autobus`; ver `ROUTE_TYPE_LABELS`).
- `color`: color hexadecimal de la línea (`route_color` de la fuente, sin
  `#`); `null` si la fuente no lo trae.
- `stops`: secuencia ordenada de paradas de un único viaje representativo
  de la línea (no todos los viajes ni el calendario completo); `[]` si la
  línea no tiene ningún viaje en la fuente (ver "hallazgos de calidad de
  datos" arriba). Cada parada excluye elementos de accesibilidad
  (ascensores, accesos...) — solo puntos de embarque reales.

### Nota sobre la captura real en esta sesión (tarea 021)

Se completó una **captura real en vivo**: la muestra commiteada en
`ingesta/capturas/samples/crtm_red_transporte_madrid_sample.json` son 12
líneas reales (3 de metro, 3 de EMT, 3 de metro ligero, 3 de cercanías,
con sus paradas reales donde la fuente las tiene), descargadas ejecutando
`python3 -m ingesta.capturas.crtm_red_transporte_madrid` tal cual contra
los feeds públicos de CRTM durante esta sesión — no son datos de ejemplo
generados a mano. No hubo ningún bloqueo de acceso que documentar: los 6
feeds GTFS son de lectura pública sin autenticación. Los ZIP completos
(hasta 72 MB el de `interurbano_cm`, no usado en la muestra por defecto)
se descargaron en memoria/disco temporal solo durante la investigación de
esta tarea para inspeccionar su estructura con herramientas de línea de
comandos, y se borraron inmediatamente después; en ningún momento se
commiteó ni se dejó en disco ningún GTFS completo.

## `capturas/agenda_recintos_madrid.py` — Agenda de grandes recintos de Madrid (deporte, conciertos, ferias; muestra puntual)

Captura la agenda de próximos eventos de los grandes recintos de Madrid que
generan picos de afluencia conocidos con antelación: un partido en el
Bernabéu, un concierto en el WiZink Center/Movistar Arena, una feria en
IFEMA... En vez de una fuente distinta por tipo de evento, captura **por
recinto**: cada gran recinto tiene su propia agenda con todo lo que allí
ocurre.

### Hallazgo clave: reutiliza la agenda de esMadrid, no scrapea cada recinto

Antes de escribir un scraper por recinto se investigó, para cada uno, si
existía una fuente estructurada propia. El hallazgo principal es que **la
agenda de esMadrid ya capturada en `agenda_eventos_madrid.py` (tarea 017,
dataset `agenda_turismo_esmadrid`) incluye, con nombre de recinto explícito
(`nombrert`), eventos reales de 6 de los 7 recintos objetivo** — verificado
en vivo descargando el feed completo (~4,4 MB, 1.050 eventos) durante esta
sesión:

| `venue_id`           | Recinto (enunciado)            | `nombrert` en esMadrid                          | eventos reales |
|-----------------------|----------------------------------|---------------------------------------------------|-----------------|
| `bernabeu`            | Estadio Santiago Bernabéu        | `Estadio Bernabéu`                                 | 12 |
| `metropolitano`       | Estadio Cívitas Metropolitano    | `Estadio Riyadh Air Metropolitano`                  | 15 |
| `movistar_arena`      | WiZink Center / Movistar Arena   | `Movistar Arena`                                    | 89 |
| `ifema_madrid`        | IFEMA Madrid                     | `IFEMA MADRID`, `IFEMA Palacio Municipal`           | 51 + 1 |
| `hipodromo_zarzuela`  | Hipódromo de la Zarzuela         | `Hipódromo de la Zarzuela` (espacio inicial en la fuente) | 2 |
| `caja_magica`         | Caja Mágica                      | `Caja Mágica`                                       | 4 |

Por eso este módulo **no hace ninguna petición HTTP nueva**: filtra por
nombre de recinto el mismo feed XML que ya descarga
`agenda_eventos_madrid.fetch_esmadrid_services_raw`, y reutiliza
`normalize_esmadrid_event` para el parseo de cada `<service>`. Es la fuente
más estructurada, estable y ya verificada disponible para estos recintos —
reutilizarla evita mantener un scraper HTML frágil por cada sitio web.

### Corrección sobre la lista de recintos del enunciado: solo 6 recintos físicos, no 7

Se investigó en vivo (varias webs de venta de entradas independientes,
contrastadas entre sí) y se confirmó que **"WiZink Center" y "Movistar
Arena" son el mismo recinto físico** (el Palacio de Deportes de la
Comunidad de Madrid, Av. de Felipe II): cambió de nombre comercial el 1 de
enero de 2025 al renovarse el patrocinio, no son dos recintos distintos. El
"Palacio de Vistalegre" que el enunciado asocia entre paréntesis a Movistar
Arena ("antiguo Palacio de Vistalegre") es en realidad **un edificio
distinto, en Carabanchel** — la propia agenda de esMadrid lo confirma con
una entrada separada, `"Palacio Vistalegre Arena"` (20 eventos reales),
distinta de `"Movistar Arena"` (89 eventos reales). De los 7 nombres del
enunciado solo hay 6 recintos físicos distintos: se implementa un único
`movistar_arena` que cubre lo que el enunciado listaba como "WiZink Center"
y "Movistar Arena" a la vez.

Los dos estadios de fútbol también han cambiado de nombre comercial por
patrocinio (el Cívitas Metropolitano del enunciado pasó a llamarse "Estadio
Riyadh Air Metropolitano" en 2025); `VENUES` documenta ambos nombres pero el
filtrado hace *match* por el nombre exacto que usa la fuente en el momento
de esta captura — si vuelve a cambiar el patrocinador, habrá que actualizar
`esmadrid_names`.

### WiZink Center como dominio propio: bloqueado, y ya no hace falta

Se investigó `wizinkcenter.es` de forma independiente, antes de descubrir
que es el mismo recinto que Movistar Arena: devuelve `403 Forbidden` en
**toda petición, incluido `/robots.txt`**, con cualquier User-Agent
probado — un bloqueo de WAF a nivel de dominio completo (a diferencia del
bloqueo de esmadrid.com en la tarea 017, que sí se resolvía con un
User-Agent de navegador). No se investigó más porque, una vez confirmado
que es el dominio heredado de un recinto ya cubierto vía esMadrid como
`movistar_arena`, forzar ese scraping no aporta cobertura nueva.

### Otras fuentes investigadas y descartadas

- **IFEMA Madrid tiene su propia agenda con JSON-LD `schema.org/Event`**
  (`https://www.ifema.es/calendario`, verificado en vivo: 43 bloques
  `Event` reales con `name`/`startDate`/`endDate`/`location`) — una fuente
  excelente, descartada a favor de esMadrid solo por simplicidad (un único
  mecanismo de captura para los 6 recintos). Queda anotada por si una
  tarea futura prefiere esta fuente directa para IFEMA en concreto.
- **Calendario oficial de Real Madrid / Atlético de Madrid**
  (`realmadrid.com`, `atleticodemadrid.com`): aplicaciones Angular pesadas
  sin datos embebidos en el HTML servido (todo vía APIs internas no
  documentadas) — descartado por ser scraping frágil de una API privada.
- **`fixturedownload.com`** publica el calendario 2026/27 de LaLiga en
  JSON sin autenticación, con el estadio incluido (`Location`) — la fuente
  más rica encontrada para fútbol. **Se descartó explícitamente**: su
  `robots.txt` incluye `User-agent: ClaudeBot` / `Disallow: /` (bloqueo
  dirigido específicamente a los rastreadores de Claude, además de
  `Content-Signal: ai-train=no` a nivel de sitio) — se respeta esa señal
  aunque el acceso fuera técnicamente posible.
- **`openfootball/football.json`** (GitHub, datos abiertos de dominio
  público): tiene el calendario completo de LaLiga por temporada, pero no
  incluye el estadio y, verificado en vivo, la temporada 2026-27 aún no
  estaba publicada en la fecha de esta captura (solo llega hasta 2025-26,
  finalizada).

### Aforo: campo presente pero siempre `null`, deliberadamente

El esquema incluye `capacity`, pero se deja siempre a `null`: esMadrid no
publica aforo por evento, y las cifras de aforo "oficiales" investigadas en
vivo (en particular el nuevo Bernabéu tras su reforma) están contradichas
entre sí por distintas fuentes de prensa (entre 78.297 y 85.500, sin cifra
oficial pública del club) — se prefirió dejar el campo vacío antes que
incrustar un número no verificable.

### Hallazgo colateral: título con entidades HTML sin decodificar en `agenda_eventos_madrid.py`

Al inspeccionar eventos reales de fútbol (`"Real Madrid - M&aacute;laga
CF"`) se descubrió que algunas entradas del feed de esMadrid traen el
título con entidades HTML sin decodificar dentro de su propio `CDATA` de
origen, a diferencia del resto del feed que usa UTF-8 directo. Es un
problema de calidad de datos de la fuente, no de este proyecto, pero
`agenda_eventos_madrid.normalize_esmadrid_event` no lo corregía (sí lo
hacía ya para `description`/`schedule_text`, pero no para `title`). Se
corrigió en esa función como parte de esta tarea (aplicando
`html.unescape` también al título), ya que este módulo construye sus
registros sobre ella.

### Dos modos, mismo patrón que `bluesky_menciones_madrid.py` (tarea 016)

- `fetch_venue_agenda(venue_id, ...)`: agenda de un recinto concreto —
  modo bajo demanda, para cuando el asistente conversacional necesite
  responder sobre un recinto concreto.
- `sweep_all_venues(...)`: agenda de todos los recintos de `VENUES` —
  descarga el feed de esMadrid una sola vez y filtra en memoria para cada
  recinto, pensado para un futuro barrido programado a diario.

### Esto es una captura puntual de muestra

Igual que `agenda_eventos_madrid.py` y el resto de tareas 003-021, no tiene
modo `--interval-seconds` ni bucle, y no escribe en la capa Bronze
particionada.

### Ejecutar

```bash
python3 -m ingesta.capturas.agenda_recintos_madrid
```

### Variables de entorno

Reutiliza las mismas variables que `agenda_eventos_madrid.py` para el
acceso al feed de esMadrid (`AGENDA_MADRID_ESMADRID_URL`,
`HTTP_TIMEOUT_SECONDS`, `HTTP_MAX_RETRIES`, `HTTP_RETRY_BACKOFF_SECONDS`),
más:

| Variable | Descripción | Por defecto |
|---|---|---|
| `AGENDA_RECINTOS_SAMPLE_SIZE_PER_VENUE` | Máximo de eventos por recinto en la muestra | `3` |

### Esquema normalizado (por registro)

```json
{
  "schema_version": 1,
  "source": "agenda_recintos_madrid",
  "upstream_source": "agenda_turismo_esmadrid",
  "venue_id": "bernabeu",
  "venue_name": "Estadio Santiago Bernabéu (Real Madrid)",
  "event_id": "109312",
  "title": "Real Madrid - Málaga CF (LALIGA EA SPORTS)",
  "event_type": "deporte",
  "category": "Eventos > Deporte > Fútbol",
  "start_datetime": "2026-08-30",
  "end_datetime": "2026-08-30",
  "schedule_text": "17:00 h",
  "capacity": null,
  "url": "https://www.esmadrid.com/agenda/real-madrid-malaga-cf-laliga-ea-sports-estadio-bernabeu",
  "captured_at": "2026-08-14T04:05:07.219305+00:00"
}
```

- `venue_id`/`venue_name`: recinto normalizado (clave de `VENUES` y nombre
  legible); `upstream_source` indica de qué captura ya existente procede
  el dato (siempre `agenda_turismo_esmadrid` en esta versión).
- `event_type`: `"deporte"`/`"concierto"`/`"otro"`, inferido del segundo
  nivel de `category` (ver `_infer_event_type`); `null` si la fuente no
  trae categoría.
- `capacity`: siempre `null` en esta versión (ver "Aforo" arriba).

### Nota sobre la captura real en esta sesión (tarea 022)

Se completó una **captura real en vivo**: la muestra commiteada en
`ingesta/capturas/samples/agenda_recintos_madrid_sample.json` son 17
eventos reales (3 por recinto, salvo el Hipódromo de la Zarzuela con 2,
todos los que había en el feed) de los 6 recintos cubiertos, obtenidos
ejecutando `python3 -m ingesta.capturas.agenda_recintos_madrid` tal cual
durante esta sesión — no son datos de ejemplo generados a mano. No hubo
ningún bloqueo de acceso que documentar para el mecanismo de captura en sí
(reutiliza el acceso a esMadrid ya verificado en la tarea 017); el único
recinto sin cobertura es WiZink Center, documentado arriba en
`UNAVAILABLE_VENUES` con el motivo (es el mismo recinto que `movistar_arena`
bajo un nombre comercial anterior, no un recinto distinto sin capturar).

## `capturas/cartelera_cines_madrid.py` — Cartelera y horarios de cines de Madrid (muestra puntual)

Ir al cine es uno de los "planes alternativos" que Madroño podría recomendar
(ver `documents/Memoria_TFM FV.docx`). Complementa a `agenda_recintos_madrid.py`
(tarea 022): a diferencia de un partido en el Bernabéu, no hay una API
oficial de las grandes cadenas de cines (Cinesa, Yelmo Cines).

### Investigación de la fuente: JSON-LD sí, pero no `ScreeningEvent`

Antes de escribir ningún scraper se investigó, tal como pedía el enunciado,
si las páginas de cartelera exponen `schema.org/ScreeningEvent` en JSON-LD:

- **`cinesa.es`**: bloqueado por Cloudflare a nivel de dominio completo
  (`403` con página de challenge incluso en `/robots.txt`, con cualquier
  User-Agent probado, verificado en vivo) — mismo tipo de bloqueo de WAF ya
  documentado para `wizinkcenter.es` en la tarea 022.
- **`yelmocines.es`**: no bloqueado, pero aplicación ASP.NET clásica sin
  URLs de cartelera adivinables ni JSON-LD; forzar su scraping habría
  exigido primero mapear a mano su navegación (selector de ciudad/cine),
  con el riesgo de fragilidad que el enunciado pedía evitar.
- **SensaCine** (`sensacine.com`, Webedia/AlloCiné): agrega la cartelera de
  **todas** las cadenas de España, Cinesa y Yelmo incluidas, en una única
  web. Verificado en vivo: sí publica JSON-LD, pero solo
  `schema.org/MovieTheater` (nombre, dirección, aforo de salas) e
  `ItemList` (enlaces a fichas de película); **no publica
  `ScreeningEvent`** en ningún JSON-LD — los horarios concretos no están en
  el bloque estructurado.

Sí se encontró algo casi tan bueno: los horarios están en el HTML servido
(sin necesidad de ejecutar JavaScript — `curl` sin cabecera de navegador ya
devuelve el HTML completo, servido del lado del servidor) como
**atributos `data-*` explícitos y ya tipados** en cada franja horaria
(`data-showtime-time="2026-08-13T22:10:00+02:00"`, `data-showtime-id`,
`data-experiences` con la versión/formato en JSON), pensados por el propio
sitio para que su JavaScript de reserva los lea — no texto libre que haya
que interpretar. Se eligió SensaCine como fuente única para ambas cadenas.

### Términos de uso de SensaCine: zona gris, igual que la tarea 012

Se leyeron en vivo los términos legales
(`https://www.sensacine.com/servicios/terminos/`): reservan expresamente la
reproducción/distribución del sitio y limitan su uso a "privado y
personal", prohibiendo cualquier fin comercial sin consentimiento escrito
de SensaCine. Es el mismo tipo de zona gris ya documentado en la tarea 012
(`afluencia_lugares_madrid.py`, apartado 6.8 de la memoria): admisible como
muestra pequeña en el marco académico de este TFM, **no** apto para
escalar a scraping masivo o uso comercial sin revisar antes esos términos
con la propia SensaCine. `robots.txt` no añade restricción adicional
relevante (solo excluye rutas de utilidades internas y algunos bots de
entrenamiento de IA por nombre; ninguno coincide con este cliente,
verificado en vivo — a diferencia de la tarea 022, aquí no hay ninguna
señal `Disallow: /` dirigida a un User-Agent de Claude). El `User-Agent` de
este módulo se identifica honestamente
(`madrono-tfm-ingesta/0.1 (+madrono.ucm@gmail.com; academic research)`,
mismo patrón que `bluesky_menciones_madrid.py`), sin suplantar un
navegador.

### Deduplicación por `data-showtime-id`: un defecto real de la fuente

Se descubrió en vivo, inspeccionando el HTML real de Cinesa Proyecciones,
que algunas versiones de idioma aparecen **duplicadas byte a byte en el
propio HTML de origen** (mismo bloque "En V.O.S.E.", mismo
`data-showtime-id`, repetido dos veces seguidas) — un defecto de plantilla
de SensaCine, no un error de este parser. `fetch_cinema_showtimes` deduplica
por `data-showtime-id` dentro de cada cine para no producir horarios
repetidos.

### Dos modos

- `fetch_cinema_showtimes(cinema_id, ...)`: cartelera completa de un cine
  concreto (película + horario + versión de idioma) — modo bajo demanda
  para el asistente conversacional.
- `sweep_premieres(...)`: estrenos destacados de la semana en España (no
  hay estrenos "solo Madrid": SensaCine publica una única lista nacional) —
  pensado para una futura captura programada ligera y diaria, ya que la
  cartelera cambia semanalmente pero puede haber cambios/cancelaciones
  puntuales de un día para otro.

### Cines cubiertos

`CINEMAS` registra 4 cines (2 Cinesa + 2 Yelmo) verificados en vivo
mediante su identificador interno de SensaCine (`E0xxx`, visible en la URL
de la ficha de cada cine); `DEFAULT_CINEMA_IDS` (los usados por la muestra
por defecto) se limita a **uno de cada cadena**, tal como pedía el
objetivo de la tarea:

| `cinema_id` | Cadena | `sensacine_id` | Nombre |
|---|---|---|---|
| `cinesa_proyecciones` (por defecto) | Cinesa | `E0402` | Cinesa Proyecciones |
| `cinesa_mendez_alvaro` | Cinesa | `E0247` | Cinesa Méndez Álvaro |
| `yelmo_ideal` (por defecto) | Yelmo | `E0621` | Yelmo Cines Ideal |
| `yelmo_la_vaguada` | Yelmo | `E0459` | Yelmo Cines La Vaguada |

### Esto es una captura puntual de muestra

Igual que el resto de tareas 003-022, no tiene modo `--interval-seconds` ni
bucle, y no escribe en la capa Bronze particionada.

### Ejecutar

```bash
python3 -m ingesta.capturas.cartelera_cines_madrid
```

### Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `SENSACINE_BASE_URL` | URL base de SensaCine | `https://www.sensacine.com` |
| `CARTELERA_CINES_MADRID_CINEMA_IDS` | Cines a capturar en la muestra (lista separada por comas, claves de `CINEMAS`) | `cinesa_proyecciones,yelmo_ideal` |
| `CARTELERA_CINES_MADRID_SHOWTIMES_LIMIT` | Máximo de horarios por cine en la muestra | `6` |
| `CARTELERA_CINES_MADRID_PREMIERES_LIMIT` | Máximo de estrenos en la muestra | `6` |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` / `HTTP_RETRY_BACKOFF_SECONDS` | Igual que el resto de productores del proyecto | `15.0` / `3` / `2.0` |

### Esquema normalizado — horario de sesión (`fetch_cinema_showtimes`)

```json
{
  "schema_version": 1,
  "source": "cartelera_cines_madrid",
  "cinema_id": "cinesa_proyecciones",
  "chain": "cinesa",
  "cinema_name": "Cinesa Proyecciones",
  "address": "Calle de Fuencarral 136",
  "postal_code": "28001",
  "locality": "Madrid",
  "screen_count": 8,
  "movie_title": "Spider-Man: Brand New Day",
  "movie_url": "https://www.sensacine.com/peliculas/pelicula-276608/",
  "language_version": "En Versión doblada",
  "experiences": ["Format.Projection.Digital"],
  "showtime_datetime": "2026-08-14T15:50:00+02:00",
  "showtime_id": "80287958721",
  "captured_at": "2026-08-14T04:17:48.423713+00:00"
}
```

### Esquema normalizado — estreno de la semana (`sweep_premieres`)

```json
{
  "schema_version": 1,
  "source": "cartelera_cines_madrid",
  "record_type": "estreno_semana",
  "movie_title": "Cuentra atrás",
  "movie_url": "https://www.sensacine.com/peliculas/pelicula-326598/",
  "release_date": "2026-08-14",
  "duration_minutes": 97,
  "genres": ["Acción", "Suspense"],
  "captured_at": "2026-08-14T04:17:48.423713+00:00"
}
```

### Nota sobre la captura real en esta sesión (tarea 023)

Se completó una **captura real en vivo**: la muestra commiteada en
`ingesta/capturas/samples/cartelera_cines_madrid_sample.json` son 18
registros reales (6 horarios de Cinesa Proyecciones + 6 de Yelmo Cines
Ideal + 6 estrenos de la semana), obtenidos ejecutando
`python3 -m ingesta.capturas.cartelera_cines_madrid` tal cual durante esta
sesión — no son datos de ejemplo generados a mano. No hubo ningún bloqueo
de acceso que documentar para la fuente elegida (SensaCine); el único
bloqueo encontrado fue el de `cinesa.es` como dominio propio, descartado a
favor de SensaCine (ver arriba).

## Tests

No dependen de la red: usan fixtures con copias/ejemplos de las respuestas
reales de cada fuente (`ingesta/tests/fixtures/`).

```bash
python3 -m unittest discover -s ingesta/tests -t .
```
