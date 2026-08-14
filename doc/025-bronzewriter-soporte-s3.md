# 025 — BronzeWriter: soporte de escritura real en S3

## Qué se implementó

`ingesta/capturas/bronze.py` (`BronzeWriter`, tarea 002) gana un segundo
backend de escritura, elegido automáticamente según la forma de `base_path`:

- **Local (por defecto)**: cualquier ruta que no empiece por `s3://`.
  Comportamiento sin cambios respecto a la tarea 002 — escribe con
  `Path.open()` en disco.
- **S3** (nuevo): rutas `s3://<bucket>/<prefijo-opcional>`. Escribe con
  `boto3.client("s3").put_object(...)`, usando el mismo esquema de
  particionado (`<dataset>/fecha=.../hora=.../<timestamp>_<sufijo>.json`)
  como key del objeto.

Es un único cambio en la clase compartida: ningún productor individual
(`trafico_madrid.py` y los que se añadan en el futuro) necesita tocarse para
poder escribir en S3 — basta con apuntar `BRONZE_BASE_PATH` a
`s3://madrono-tfm-dev-bronze-222234418587/` (el bucket real de la tarea 015).

## Decisiones de diseño

- **Detección del backend por la forma de `base_path`, no por un flag
  aparte**: `str(base_path).startswith("s3://")` es la única señal —
  consistente con cómo ya se documentaba desde la tarea 002 que
  `BRONZE_BASE_PATH` sería el único punto de cambio para migrar a S3.
- **Tipo de retorno de `write_batch` condicional al backend**: `Path` en
  modo local (sin cambios, para no romper a quien ya inspeccione
  `out_path.exists()`/`.parent`, como hacía el test de la tarea 002), `str`
  con la URI `s3://bucket/key` en modo S3. Documentado explícitamente en el
  docstring del módulo y en el README, ya que es el único cambio de
  contrato observable desde fuera de la clase.
- **`boto3.client("s3")` se crea una vez en `__init__`, no en cada
  `write_batch`**: crear el cliente no hace ninguna llamada de red (solo
  resuelve configuración/credenciales), así que no hay coste en crearlo por
  adelantado, y evita recrearlo en cada lote si un productor futuro llama a
  `write_batch` repetidamente (p.ej. en modo `--interval-seconds`).
- **Sin credenciales explícitas en el código**: `boto3.client("s3")` resuelve
  credenciales automáticamente por la cadena estándar de AWS — en la EC2 de
  ingesta, las del rol de instancia `madrono-tfm-dev-ingestion-role`
  aplicado en la tarea 015, que ya está restringido a escribir solo en el
  bucket Bronze. No hace falta ninguna variable de entorno nueva de
  credenciales.
- **`boto3` añadido a `ingesta/requirements.txt`** aunque ya estaba
  disponible en este entorno concreto (verificado, `1.40.72`): la
  dependencia debe declararse explícitamente para que cualquier otro
  entorno (otro desarrollador, CI) pueda instalarla, no asumirse presente
  porque esta EC2 ya la tenga.

## Restricción respetada: sin escritura real al bucket S3

Ningún test de esta tarea llama a AWS real: `test_bronze.py` sustituye
`ingesta.capturas.bronze.boto3.client` por un doble (`unittest.mock.patch` +
`MagicMock`) y verifica los argumentos exactos pasados a `put_object`
(bucket, key, body, content-type), sin red ni credenciales reales. Tal como
pedía el enunciado, el código queda listo y probado, pero activar
`BRONZE_BASE_PATH=s3://...` contra el bucket real en producción (cron/systemd
timer de cada productor) es una decisión de despliegue posterior, no tomada
en esta tarea.

## Tests

`ingesta/tests/test_bronze.py` (nuevo, 5 tests): modo local (fichero
particionado creado correctamente, ruta `Path` — mismo caso que ya cubría
`test_trafico_madrid.py` desde la tarea 002, más una comprobación de que un
`Path` como `base_path` nunca se interpreta como S3) y modo S3 con doble de
`boto3` (bucket/key/body/content-type esperados en `put_object`, prefijo
opcional antepuesto a la key, URI de retorno con forma `s3://bucket/key`, y
que no se toca el sistema de ficheros local en este modo). El test existente
`BronzeWriterTests` en `test_trafico_madrid.py` (tarea 002) no se tocó y
sigue en verde sin cambios, confirmando que el modo local es idéntico.
Suite completa del proyecto verificada tras el cambio: **230 tests** (225
previos + 5 nuevos), todos en verde.

## Relevante para tareas futuras

- Cualquier productor nuevo que use `BronzeWriter` ya soporta S3 sin ningún
  cambio propio — el backend se decide solo por el valor de
  `BRONZE_BASE_PATH`.
- El siguiente paso natural (fuera de esta tarea) es decidir cómo y cuándo
  activar `BRONZE_BASE_PATH=s3://madrono-tfm-dev-bronze-222234418587/` en
  real para cada productor desplegado (los que ya corren en Lambda+
  EventBridge según la tarea de migración a producción mencionada en el
  contexto, y los que aún se ejecutan solo bajo demanda) — probablemente
  como variable de entorno de la propia Lambda/cron, no como cambio de
  código.
- `write_batch` devuelve `str` en modo S3 y `Path` en modo local: si una
  tarea futura empieza a depender del valor de retorno para algo más que
  loguearlo (p.ej. pasar la ubicación a un paso posterior del pipeline),
  debe tratar ambos casos o normalizar a string explícitamente — no asumir
  que siempre es un `Path`.
