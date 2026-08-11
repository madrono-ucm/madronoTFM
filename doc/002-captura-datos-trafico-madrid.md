# 002 — Captura de datos de tráfico de Madrid (primer productor de ingesta)

## Qué se implementó

Primer productor de datos de la Fase 1 (Ingesta) del proyecto, en un nuevo
directorio `ingesta/` en la raíz del repo (paralelo a `infra/`):

- `ingesta/capturas/bronze.py`: `BronzeWriter`, un escritor genérico de la
  capa Bronze. Escribe un lote de registros (lista de dicts JSON-serializables)
  en un único fichero JSON, particionado como
  `<base>/<dataset>/fecha=YYYY-MM-DD/hora=HH/<timestamp>_<sufijo>.json`
  (escritura atómica vía fichero temporal + `rename`). `<base>` es
  configurable, pensado para reutilizarse tal cual por todos los futuros
  productores (transporte público, bicicleta compartida, calidad del aire,
  ruido, meteorología).
- `ingesta/capturas/trafico_madrid.py`: descarga el feed público de
  intensidad de tráfico en tiempo real del Ayuntamiento de Madrid
  (servicio Informo, dataset "Tráfico. Intensidad y velocidad" de
  datos.madrid.es) — `https://informo.madrid.es/informo/tmadrid/pm.xml` —,
  lo normaliza a un esquema mínimo y consistente, y lo escribe con
  `BronzeWriter` en el dataset `trafico`. Incluye reintentos simples con
  backoff lineal ante fallos de red, logging, y dos modos de ejecución: una
  captura puntual (pensada para invocarse desde cron/systemd timer) o un
  bucle continuo (`--interval-seconds N`) para poder correr como proceso de
  larga duración sin depender de un scheduler externo.
- `ingesta/tests/`: tests con `unittest` (stdlib, sin añadir `pytest` como
  dependencia) que verifican el parseo/normalización y la escritura a Bronze
  usando un fixture (`fixtures/pm_sample.xml`) con una copia reducida de una
  respuesta real del feed — no hacen ninguna llamada de red.
- `ingesta/requirements.txt` (solo `requests`) y `ingesta/README.md` con
  instrucciones de instalación/ejecución, variables de entorno y el esquema
  normalizado.
- `.gitignore` raíz ampliado para no commitear el aterrizaje local de Bronze
  (`ingesta/bronze/`, `/bronze/`).

**Verificado en vivo**: la fuente es accesible sin credenciales desde este
entorno; se ejecutó `python3 -m ingesta.capturas.trafico_madrid` contra el
feed real y produjo un fichero con 4893 registros normalizados en
`bronze/trafico/fecha=2026-08-11/hora=23/*.json`. No hizo falta usar datos
mock (la restricción de la tarea sobre red no aplicable no se dio).

## Esquema normalizado

Por registro: `schema_version`, `source`, `point_id`, `measured_at` (UTC,
timestamp global del feed convertido desde hora de Madrid), `ingested_at`
(UTC, instante de la descarga), `description`, `access_code`, `subarea`,
`intensity_vph`, `occupancy_pct`, `load_pct`, `service_level`,
`saturation_intensity_vph`, `has_error`/`error_code`, y `location`
(`x`/`y`/`srid`). Detalle completo en `ingesta/README.md`.

## Decisiones de diseño (por qué)

- **Ubicación `ingesta/capturas/`** (en vez de `ingesta/capturas/trafico_madrid.py`
  suelto): se separó un `bronze.py` compartido del módulo específico de la
  fuente, porque el propio objetivo de la tarea es "sentar el patrón" para
  los próximos productores — cada fuente futura solo necesitará su propio
  `<fuente>.py` con `fetch` + `normalize_record` + `parse_records`,
  reutilizando `BronzeWriter` sin cambios.
- **Sin Kafka, con `TODO(kafka)` explícito** en el docstring del módulo y
  junto a `capture_once`, tal como pedía la tarea: cuando exista un broker
  (infraestructura futura), la función de normalización (`normalize_record`)
  queda ya aislada de la escritura, así que producir a un topic Kafka además
  de/en vez de Bronze será un cambio local a `capture_once`.
- **No se reproyectan las coordenadas a lat/lon**: el feed las da en UTM
  ETRS89 huso 30N (EPSG:25830, con coma decimal). Se normalizan a `float`
  con punto decimal pero se mantienen en su sistema de coordenadas original
  (`location.x`/`location.y`/`location.srid`) en vez de convertir a WGS84,
  para no añadir una dependencia de geoprocesado (`pyproj`) que esta tarea de
  Bronze no necesita — Bronze debe ser fiel a la fuente. Si una tarea de
  Silver/Gold necesita lat/lon, es una transformación a añadir ahí.
- **Registros con error de sensor (`error=S`, campos vacíos) se conservan**,
  normalizando los campos numéricos ausentes a `null` en vez de descartar el
  registro — Bronze debe reflejar la fuente tal cual, incluidos sus errores;
  filtrarlos sería una decisión de capas superiores (Silver).
- **Tests con `unittest` de la librería estándar**, no `pytest`: el entorno
  de este workspace no tenía `pytest` instalado y el repo todavía no fija
  ninguna convención de testing en Python; usar solo stdlib evita añadir una
  dependencia de desarrollo y mantiene `python3 -m unittest discover`
  ejecutable sin instalar nada más allá de `requirements.txt`.
- **Un único fichero JSON por captura** (lista de registros), no un fichero
  por registro: ~4900 puntos de medida por captura harían que un fichero por
  registro fuera poco práctico (miles de ficheros muy pequeños por hora); un
  lote por captura es el patrón habitual en Bronze para fuentes de tipo
  snapshot/polling.

## Relevante para tareas futuras

- El patrón `BronzeWriter` + `fetch_raw_*` + `normalize_record` +
  `parse_records` + `capture_once` de `trafico_madrid.py` está pensado para
  copiarse tal cual en los próximos productores (`ingesta/capturas/<fuente>.py`),
  cambiando solo la fuente, el parseo y el esquema normalizado.
- `BRONZE_BASE_PATH` apunta hoy a disco local (`./bronze` por defecto). Nadie
  ha montado todavía el bucket S3 Bronze de la tarea 001 en este entorno; el
  día que se haga (p.ej. vía un punto de montaje S3 como `mountpoint-s3` o
  subiendo el directorio local con un job aparte), bastará con cambiar esa
  variable de entorno, sin tocar código.
- No hay todavía ningún mecanismo de scheduling desplegado (cron, systemd
  timer, Lambda periódica...) que invoque este productor automáticamente:
  esta tarea deja el script listo para ejecutarse periódicamente, pero
  desplegar ese scheduling (o una Lambda que use el rol de ingesta de la
  tarea 001) queda fuera de alcance y pendiente de una tarea futura.
- Sigue sin existir ningún broker Kafka; el punto de conexión queda marcado
  con `TODO(kafka)` en `trafico_madrid.py`.
