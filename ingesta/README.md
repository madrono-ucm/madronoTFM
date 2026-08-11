# ingesta

Productores de datos que capturan fuentes abiertas y las aterrizan en la capa
Bronze del lakehouse (Fase 1 del proyecto, ver `documents/Memoria_TFM FV.docx`,
apartado 6.1). Cada fuente (tráfico, transporte público, bicicleta
compartida, calidad del aire, ruido, meteorología...) es un módulo bajo
`ingesta/capturas/` que sigue el mismo patrón: descarga -> normaliza a un
esquema mínimo y consistente -> escribe un lote en Bronze vía
`ingesta.capturas.bronze.BronzeWriter`.

Todavía no hay un broker Kafka desplegado (ver tarea 001), así que estos
productores están pensados para ejecutarse periódicamente (cron, systemd
timer, o su propio modo `--interval-seconds`) y escriben directamente a
disco. El punto donde se conectaría un productor Kafka está marcado con
`TODO(kafka)` en cada módulo.

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

## Tests

No dependen de la red: usan un fixture con una copia reducida de una
respuesta real del feed (`ingesta/tests/fixtures/pm_sample.xml`).

```bash
python3 -m unittest discover -s ingesta/tests -t .
```
