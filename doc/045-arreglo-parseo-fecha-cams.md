# 045 — Arreglo del parseo de NetCDF de CAMS (ValueError en producción real)

## Contexto

Con las credenciales de Copernicus ADS ya funcionando y la licencia del
dataset aceptada (tarea 019), una invocación real de
`madrono-tfm-dev-cams_calidad_aire` dejó de fallar con 403 pero empezó a
fallar con `ValueError: Incorrectly formatted CF date-time unit_string` en
`normalize_forecast_file`. El fixture de desarrollo usado en la tarea 019
asumía un formato CF estándar (`"hours since 1900-01-01..."`) para
`time.units` que nunca se había podido contrastar contra un fichero real
(bloqueo de registro en ese momento). Con acceso real esta tarea confirma
que ese formato no es el que devuelve la API.

## Diagnóstico: tres bugs reales, no solo uno

Se reprodujo la petición real (`_fetch_forecast_zip_bytes`, con
`CAMS_ADS_API_KEY` real leída de SSM
`/madrono-tfm/dev/secrets/cams-ads-api-key`) contra la corrida de
`2026-08-15` (la de `2026-08-16` aún no estaba publicada, ver más abajo) y se
inspeccionó el `.nc` real descargado. Aparecieron **tres** problemas de
parseo, no solo el de fechas del enunciado — los otros dos también hacían
fallar o corrompían silenciosamente cualquier invocación real, así que se
consideraron parte de "hacer que `normalize_forecast_file` parsee
correctamente el fichero real" y se corrigieron en la misma tarea (a
diferencia del hallazgo sobre `dust_conc`, ver más abajo, que no bloquea
nada y se deja para una tarea de seguimiento tal como pedía el enunciado).

### 1. Formato real de `time.units` (el bug del enunciado)

El `.nc` real tiene `time.units = "hours"` — **sin** cláusula CF `"since
<referencia>"` — y **no tiene ninguna variable `forecast_reference_time`**.
La fecha de referencia real está en `time.long_name`:
`"FORECAST time from 20260815"` (`AAAAMMDD`). Verificado en dos corridas
reales distintas (con pedidos de contaminantes distintos), mismo formato en
ambas.

**Arreglo:** `_parse_time_variable` (nuevo) intenta primero el formato CF
estándar (`"since" in units`, delega en `netCDF4.num2date`, por si la API
cambiara de formato en el futuro) y, si no está presente, parsea la fecha de
referencia de `time.long_name` con `_parse_reference_date` y calcula cada
`valid_datetime` como `referencia + timedelta(**{unidad: valor})`. También
se usa esa misma fecha de referencia (no `valid_datetimes[0]`) como
`forecast_issued_at` cuando no hay `forecast_reference_time`, para que
`leadtime_hour` sea correcto incluso si `CAMS_LEADTIME_HOURS` no empezara en
`"0"`.

### 2. Dimensión `level` no contemplada

Las variables de contaminante reales tienen forma
`(time, level, latitude, longitude)` (con `level` de tamaño 1: la petición
siempre pide un único nivel, `CaptureConfig.level`), no
`(time, latitude, longitude)` como asumía el fixture original. Indexar por
posición fija (`values[t_idx, lat_idx, lon_idx]`) fallaba con
`TypeError: Only length-1 arrays can be converted to Python scalars` contra
cualquier fichero real.

**Arreglo:** `_grid_value` (nuevo) indexa por nombre de dimensión
(`variable.dimensions`), no por posición fija — funciona tanto con la forma
real (4D) como con la forma sin `level` (3D, por si la API la sirviera así
algún día).

### 3. Convención de longitud `[0, 360)`, no `[-180, 180)`

La variable `longitude` real trae valores como `356.15/356.25/356.35` (no
`-3.85/-3.75/-3.65`). Sin normalizar, `_nearest_index` comparaba esos
valores contra `MADRID_CENTER_LON = -3.7038` y elegía sistemáticamente el
punto de rejilla más al oeste (el "menos lejano" de una comparación sin
sentido), además de guardar una longitud sin sentido en el registro
(`356.xx`).

**Arreglo:** en `normalize_forecast_file`, la longitud se normaliza a
`[-180, 180)` (`lon - 360 if lon > 180 else lon`) justo al leerla, antes de
buscar el punto más cercano y antes de guardarla en el registro.

## Hallazgo documentado, no corregido: `dust_conc`

Al pedir explícitamente `nitrogen_monoxide`/`sulphur_dioxide`/`dust` contra
la API real se confirmó que `no_conc`/`so2_conc` (el mapeo sin contrastar de
la tarea 019) son correctos, pero **`dust_conc` no lo es**: la variable real
dentro del NetCDF se llama simplemente `dust`, sin el sufijo `_conc`. Tal
como indica el enunciado de esta tarea, **no se ha corregido** (no bloquea
ninguna invocación: `normalize_forecast_file` simplemente no genera
registros de polvo, por el mismo diseño tolerante que ya documentaba el
módulo para nombres de variable no encontrados) — queda para una tarea de
seguimiento corregir `POLLUTANT_VARIABLES["dust"]` a `"dust"`. Documentado
también en el docstring del módulo.

## Tests

`ingesta/tests/test_cams_calidad_aire_madrid.py`:

- **`fixtures/cams_forecast_sample.nc` regenerado** para replicar la
  estructura real (dimensiones `time`/`level`/`latitude`/`longitude`, `time`
  con `units="hours"` y `long_name` con la fecha real, sin
  `forecast_reference_time`, `longitude` en `[0, 360)`, `units="µg/m3"` en
  las variables de contaminante) — el fixture anterior no detectaba ninguno
  de los tres bugs porque no reflejaba el formato real. Script de generación
  no commiteado (`/tmp/build_cams_fixture.py`, descartado al terminar).
- `ParseReferenceDateTests`/`ParseTimeVariableTests`: reproducen
  exactamente el `ValueError` original (`units="hours"` sin "since") contra
  dobles ligeros (sin I/O), confirman el arreglo, y verifican que el formato
  CF estándar sigue funcionando como alternativa.
- `GridValueTests`: reproduce el `TypeError` original de la dimensión
  `level` y confirma que `_grid_value` funciona con y sin esa dimensión.
- `SampleFixtureTests`: ahora exige `is_mock=False` y longitud en
  `[-180, 180]` (antes exigía `is_mock=True`, muestra real regenerada, ver
  abajo).

`ingesta/tests/test_lambda_handlers.py` (`CamsLambdaHandlerTests`): dos
tests nuevos para la extensión de `lambda_handler` (ver más abajo), sin
tocar los tests existentes de las otras 13 funciones.

Suite completa (`python3 -m unittest discover -s ingesta/tests -t .`):
**267 tests, todos en verde** (258 previos + 22 nuevos/reescritos de CAMS −
15 sustituidos, +2 de `lambda_handler`), sin regresiones en el resto de
productores.

## Extensión pequeña de `lambda_handler`: `run_date` opcional

Al intentar verificar la Lambda real desplegada, la corrida de hoy
(`2026-08-16`) no estaba publicada todavía — CAMS publica a partir de las
06:45/08:30 UTC (ver docstring del módulo), y la invocación se hizo a las
~00:23 UTC. Esto no es un bug de esta tarea, es el comportamiento normal
documentado de la fuente. Para poder verificar el código real desplegado sin
esperar 6+ horas (y sin dejar nada programado en esta EC2, restricción de la
tarea), se añadió un override opcional: `event.get("run_date")` (cadena
`AAAA-MM-DD`) fuerza la fecha de la corrida en `fetch_forecast`, con el
comportamiento por defecto (fecha UTC de hoy) sin cambios si no se pasa.
Es también una utilidad operativa real (reprocesar/backfill una corrida
concreta), no solo un artefacto de verificación.

## Reempaquetado y despliegue en AWS

Con `allow_infra_apply: true` para esta tarea, se aplicó el cambio contra la
cuenta AWS real (`222234418587`, región `eu-west-1`), acotado exactamente a
la función `cams_calidad_aire` (mismo mecanismo de `-target` que describe el
enunciado):

1. `backend.hcl`/`terraform.tfvars` regenerados desde sus `.example`
   (gitignored), con el ARN de la Lambda Layer ya publicada
   (`arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1`).
2. `terraform init -backend-config=backend.hcl`.
3. `terraform plan -var-file=terraform.tfvars -target='aws_lambda_function.producer["cams_calidad_aire"]' -out=tfplan`:
   **`Plan: 0 to add, 1 to change, 0 to destroy`** — únicamente
   `source_code_hash`/`last_modified` de esa función. Se aplicó dos veces
   (una tras el arreglo de los tres bugs de parseo, otra tras añadir el
   override de `run_date`), cada vez con el mismo alcance de un único
   recurso.
4. `terraform apply tfplan`: aplicado sin error ambas veces.
5. Un `terraform plan` sin `-target` mostró, como es esperable (mismo
   `.zip` compartido por las 14 funciones, ver doc/033/044), diferencias de
   `source_code_hash` en las otras 13 funciones — **no aplicadas**, tal como
   exigía el enunciado. También mostró el drift ya existente y documentado
   de las tareas 041/042 (Glue/Kafka, código sin aplicar) — tampoco tocado.

### Recursos AWS afectados (referencia auditable)

- **Cuenta**: `222234418587`. **Región**: `eu-west-1`.
- **Modificada in-place** (dos veces, mismo ARN/nombre): la función Lambda
  `madrono-tfm-dev-cams_calidad_aire` (`aws_lambda_function.producer["cams_calidad_aire"]`)
  — solo `source_code_hash`/`last_modified`, sin cambios de `timeout`,
  `memory_size` ni ningún otro atributo.
- No se ha creado, destruido ni modificado ningún otro recurso.

## Verificación: invocación manual real

Primera invocación (sin override, comportamiento por defecto):
`aws lambda invoke --function-name madrono-tfm-dev-cams_calidad_aire --payload '{}'`
→ falló con `400 Bad Request: Request has not produced a valid combination
of values` — la corrida de `2026-08-16` (fecha UTC de hoy) aún no estaba
publicada. Error esperado y no relacionado con esta tarea (ver sección
`run_date` arriba).

Segunda invocación (con `{"run_date": "2026-08-15"}`, tras redesplegar con
el override):

```
aws lambda invoke --function-name madrono-tfm-dev-cams_calidad_aire \
  --payload file:///tmp/cams_payload.json --cli-binary-format raw-in-base64-out \
  --region eu-west-1 /tmp/cams_invoke_result2.json
```

Resultado: `StatusCode: 200`, sin `FunctionError`:

```json
{"dataset": "cams_calidad_aire", "records_written": 16,
 "location": "s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/fecha=2026-08-16/hora=02/20260816T022619_3b9126c9.json"}
```

Se leyó el objeto escrito en Bronze y se confirmó que las 16 filas (4
contaminantes x 4 horas de leadtime) tienen fechas correctas
(`valid_datetime`/`forecast_issued_at` en hora de Madrid, `+02:00`),
longitud en rango válido (`-3.75`, no `356.25`) e `is_mock: false`.

## Muestra commiteada regenerada con datos reales

`ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json` se
regeneró con `fetch_forecast` real (corrida de `2026-08-15`, los 4
contaminantes/4 horas de leadtime por defecto): ya no tiene `is_mock: true`
como la muestra original de la tarea 019, ahora con credenciales y licencia
reales disponibles en este entorno.

## Restricciones respetadas

- No se ejecutó `terraform destroy` en ningún momento.
- El `apply` se limitó exactamente a `aws_lambda_function.producer["cams_calidad_aire"]`
  (`-target` explícito, dos veces) — no se tocó ninguna de las otras 13
  funciones ni ningún fichero `.tf` no relacionado con esta.
- No se intentó resolver el hallazgo de `dust_conc` (mapeo de nombre de
  variable incorrecto) — documentado arriba y dejado para una tarea de
  seguimiento, tal como pedía el enunciado.
- No se dejó nada programado nuevo (cron, systemd timer, bucle) en esta EC2:
  las invocaciones reales fueron puntuales (`aws lambda invoke` x2), sin
  esperar activamente a la publicación de la corrida de hoy.
- `terraform.tfvars`, `backend.hcl`, `.terraform/`, `.terraform.lock.hcl`,
  el directorio `build/` de Terraform y los `__pycache__`/ficheros
  temporales generados durante esta sesión (`/tmp/build_cams_fixture.py`,
  `/tmp/cams_*.{zip,nc,json}`) se eliminaron al terminar la tarea — nada de
  esto se commitea.

## Relevante para tareas futuras

- El bloqueo de fechas quedó resuelto junto con dos bugs más del mismo tipo
  (dimensión `level`, convención de longitud) descubiertos al contrastar
  contra datos reales por primera vez — el patrón general para el resto de
  fuentes que aún no tienen credenciales/licencia reales (si las tuvieran)
  es el mismo: los fixtures de desarrollo construidos sin acceso a un
  fichero real son la principal fuente de bugs de parseo no detectados;
  conviene regenerarlos en cuanto haya acceso real, no solo confiar en que
  "los tests pasan".
- `POLLUTANT_VARIABLES["dust"]` sigue mal (`"dust_conc"` en vez de `"dust"`)
  — corregirlo es una tarea de seguimiento pequeña y acotada, con la
  ventaja de que ya hay acceso real a la API para contrastarlo sin
  ambigüedad.
- El override `run_date` del evento de `lambda_handler` es reutilizable para
  backfills/reprocesos puntuales de una corrida concreta, o para evitar la
  ventana de "corrida de hoy aún no publicada" (06:45/08:30 UTC) si el
  `schedule` de EventBridge llegara a invocar la función antes de esa hora
  — no se ha tocado el `schedule` en sí en esta tarea.
- La cadencia/`schedule` de esta Lambda no se ha tocado (fuera del alcance
  de esta tarea, no mencionado en el enunciado).
