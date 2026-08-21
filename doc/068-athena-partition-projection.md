# 068 — Athena Partition Projection en las 30 tablas del catálogo (Silver/Gold)

## Objetivo

La tarea 066 confirmó con una consulta real que el catálogo de Glue **no** registra
particiones nuevas automáticamente (los 14 jobs Silver/Gold escriben con
`DataFrame.write.mode("append").partitionBy(...).parquet(path)`, no con un sink de
catálogo), y recomendó como solución **Athena Partition Projection** en vez de
automatizar `MSCK REPAIR TABLE`. Esta tarea aplica esa recomendación: configura
`projection.*`/`storage.location.template` en cada `aws_glue_catalog_table` de
`infra/terraform/glue.tf` y confirma con consultas reales que ya no hace falta
reparar el catálogo para ver datos nuevos.

## Corrección de una cifra: son 30 tablas, no 28

El enunciado asumía "28 tablas (`_silver`/`_gold` de los 14 datasets)". Contando
`resource "aws_glue_catalog_table"` en `glue.tf` hay **30**: `aemet_prevision_avisos`
es el único de los 14 datasets cuyo job Silver→Gold produce **dos** tablas Silver
(`aemet_prevision`, `aemet_avisos`) y **dos** tablas Gold
(`aemet_prevision_por_municipio_leadtime`, `aemet_avisos_por_zona_fecha_nivel`) en
vez de una de cada — documentado ya en la tarea 058/064 ("un único job Glue por
etapa que procesa ambas formas"), simplemente no se había reflejado en el recuento
de "28" del enunciado de esta tarea. Se ha configurado Partition Projection en las
**30** tablas reales, no en 28.

## Configuración aplicada, por patrón real de claves de partición

Se ha inspeccionado `partition_keys` de las 30 tablas en `glue.tf` en vez de asumir
que todas siguen el mismo patrón `fecha`/`hora`/`date` — y, en efecto, hay tres
grupos con forma distinta:

### Patrón A — Silver con `fecha` + `hora` (11 tablas)

`trafico`, `transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
`meteorologia`, `aforos_peatones_bicicletas`, `cartelera_cines_estrenos`,
`bluesky_menciones`, `cams_calidad_aire`, `afluencia_lugares`. Confirmado con
`ingesta/capturas/bronze.py::write_batch` (`f"hora={moment:%H}"`, 2 dígitos, hora de
Madrid) que el valor real de `hora` va siempre cero-rellenado (`"00"`.."23"`), de
ahí `digits = "2"`:

```hcl
"projection.enabled"             = "true"
"projection.fecha.type"          = "date"
"projection.fecha.range"         = "2026-08-01,NOW+1DAY"
"projection.fecha.format"        = "yyyy-MM-dd"
"projection.fecha.interval"      = "1"
"projection.fecha.interval.unit" = "DAYS"
"projection.hora.type"           = "integer"
"projection.hora.range"          = "0,23"
"projection.hora.digits"         = "2"
"storage.location.template"      = "s3://<bucket-silver>/<prefix>/fecha=${fecha}/hora=${hora}/"
```

### Patrón B — Silver/Gold con una única clave de fecha (`fecha` o `date`, 15 tablas)

Silver sin `hora` (4): `ruido`, `agenda_eventos`, `aemet_prevision`, `aemet_avisos`.
Gold con partición `date` (12): todas menos `aemet_prevision_gold` y
`cams_calidad_aire_gold` (ver excepciones abajo) — incluye `aemet_avisos_gold`, que
sí sigue este patrón pero con la clave llamada **`fecha`, no `date`** (única
tabla Gold con ese nombre; ver "Excepciones" abajo).

```hcl
"projection.enabled"             = "true"
"projection.<clave>.type"          = "date"
"projection.<clave>.range"         = "2026-08-01,NOW+1DAY"
"projection.<clave>.format"        = "yyyy-MM-dd"
"projection.<clave>.interval"      = "1"
"projection.<clave>.interval.unit" = "DAYS"
"storage.location.template"      = "s3://<bucket>/<prefix>/<clave>=${<clave>}/"
```

`range = "2026-08-01,NOW+1DAY"` (valor fijo pedido por el enunciado): cubre desde
antes del arranque de producción continua (tarea 065, 2026-08-19) hasta el día
siguiente al actual en cualquier momento, sin tener que tocar este valor según pasen
los días.

### Excepciones reales (dos tablas Gold sin ninguna clave de fecha)

Confirmado leyendo el propio `partition_keys` de `glue.tf`, no asumido a partir del
nombre de la tabla (el enunciado ya avisaba de que podía haber una excepción como
esta, poniendo como ejemplo -incorrecto en este caso concreto- `fecha_validez` en
CAMS):

- **`aemet_prevision_gold`** (`aemet_prevision_por_municipio_leadtime`): partición
  única `municipio_code` (**no** hay ninguna partición de fecha en esta tabla — la
  granularidad temporal de este Gold es `leadtime_days`, una columna normal, no una
  clave de partición). Confirmado en `ingesta/README.md` y
  `ingesta/capturas/aemet_prevision_avisos.py` que el pipeline solo ingesta un
  municipio (`AEMET_MUNICIPIO_CODE=28079`, Madrid capital) — se ha usado
  `projection.municipio_code.type = "enum"` con el único valor real conocido
  (`"28079"`), no `"date"`.
- **`cams_calidad_aire_gold`** (`cams_calidad_aire_por_contaminante_fecha_validez`):
  partición única **`pollutant`**, no `fecha_validez` como sugería el enunciado —
  `fecha_validez` es una columna normal de esta tabla (el día que predice cada
  fila), no una clave de partición; la partición real es el contaminante. Los
  valores reales están fijados en
  `procesamiento/silver_gold/cams_calidad_aire/transform.py::PLAUSIBLE_MAX_BY_POLLUTANT`:
  `NO2`, `NO`, `SO2`, `O3`, `PM2.5`, `PM10`, `polvo` (7 valores, mismo criterio que
  el resto de contaminantes de este pipeline). Se ha usado
  `projection.pollutant.type = "enum"` con esos 7 valores.

```hcl
"projection.enabled"        = "true"
"projection.municipio_code.type"   = "enum"
"projection.municipio_code.values" = "28079"
"storage.location.template" = "s3://<bucket-gold>/aemet_prevision_por_municipio_leadtime/municipio_code=${municipio_code}/"

"projection.enabled"      = "true"
"projection.pollutant.type"   = "enum"
"projection.pollutant.values" = "NO2,NO,SO2,O3,PM2.5,PM10,polvo"
"storage.location.template" = "s3://<bucket-gold>/cams_calidad_aire_por_contaminante_fecha_validez/pollutant=${pollutant}/"
```

## `storage.location.template`: escapado de `$` en Terraform

Cada tabla necesita, además de las claves `projection.*`, un
`storage.location.template` con la ruta S3 y sus marcadores `${clave}` — pero en
un string de Terraform `${...}` es interpolación de la propia configuración
(referencia al bucket real), así que los marcadores de Partition Projection se han
escrito como `$${fecha}`/`$${hora}`/etc. (`$$` → `$` literal), de forma que
Terraform interpola el nombre del bucket pero deja `${fecha}` tal cual para que lo
interprete Athena en tiempo de consulta.

## Aplicado en AWS real (región `eu-west-1`, cuenta `222234418587`)

`terraform apply` **acotado con `-target`** a las 30 `aws_glue_catalog_table`
(mismo patrón que tareas 065/066, para no arrastrar la deriva ya documentada de
Kafka/`procesamiento/`): `terraform plan -target=<30 recursos>` mostró exactamente
"Plan: 0 to add, 30 to change, 0 to destroy" — ninguna otra clase de recurso de por
medio —, y tras el `apply` un segundo `plan` con los mismos 30 `-target` mostró
"No changes." Confirmado también con `aws glue get-table` en vivo sobre 3 tablas
(`trafico` Silver, `aemet_prevision_por_municipio_leadtime`,
`cams_calidad_aire_por_contaminante_fecha_validez` Gold) que los `Parameters`
reales en AWS coinciden exactamente con lo planeado.

No se ha tocado `infra/terraform/lambda.tf` ni el código de
`procesamiento/silver_gold/` — el único fichero modificado es `glue.tf` (solo los
bloques `parameters` de las 30 tablas; ningún `partition_keys`/`storage_descriptor.
location`/columna se ha tocado).

## Reverificación: mismas 3 consultas de la tarea 066, sin `MSCK REPAIR TABLE`

| Consulta | Tarea 066 (con `MSCK REPAIR` manual) | Tarea 068 (con Partition Projection, sin repair) |
|---|---|---|
| `SELECT COUNT(*) FROM trafico` (silver) | 6 186 491 filas | **311 636 614** filas |
| `trafico_por_punto_hora` agregado por hora, `date = '2026-08-20'` (gold) | 0 filas (Gold no tenía esa partición; se repitió con `date='2026-08-16'` → 24 filas) | **24 filas** (una por hora), p.ej. hora 14 → 293.92 veh/h media sobre 64 381 puntos |
| `ruido` por estación/periodo, `fecha = '2026-08-17'` (silver), primeras 10 filas | p.ej. `RF-01`/`D` → 63.0 dB (1 lectura) | `RF-01`/`D` → 63.0 dB (**3 lecturas**) — mismo valor, más muestras acumuladas |

Las tres cumplen "igual o mayor que la 066" (mayor en los tres casos, como se
esperaba: producción real ha seguido corriendo desde entonces vía el scheduling de
la tarea 065). Ninguna de las tres ejecutó `MSCK REPAIR TABLE` ni `SHOW PARTITIONS`
antes de consultar — la propia tabla ya resuelve las particiones vía projection en
tiempo de consulta.

El salto más llamativo (`trafico` silver: 6,2M → 311,6M filas) y el hecho de que
`date = '2026-08-20'` (el día real de esta sesión) ya tenga datos en Gold de
`trafico` -- cosa que en la tarea 066 **no** ocurría (solo existía la partición
`date=2026-08-16`, hallazgo que la 065 dejó abierto como posible fallo del trigger
`CONDITIONAL`) -- confirma que el scheduling Silver→Gold de la tarea 065 sí está
funcionando en producción continua: solo hacía falta más tiempo de observación del
que permitió el presupuesto de aquella sesión. Volumen real de S3 a fecha de esta
tarea (`aws s3 ls --recursive --summarize`): Silver 236 893 objetos / 18,45 GB
(era 8494 objetos / 392 MB en la tarea 066); Gold 5600 objetos / 530 MB (era 589
objetos / 5,8 MB).

## Nota: las particiones que la tarea 066 añadió a mano con `MSCK REPAIR TABLE` quedan sin efecto

Con `projection.enabled = "true"`, Athena calcula las rutas S3 válidas en tiempo de
consulta a partir de la configuración `projection.*` y **ignora** las particiones
que pudiera haber registradas en el metastore de Glue (las que la tarea 066 añadió
a mano sobre 6 tablas) — no hace falta limpiarlas ni hacen daño, simplemente dejan
de consultarse; confirmado indirectamente por el propio resultado (`trafico`
devuelve 311M filas reales sin haber ejecutado ningún `MSCK REPAIR` en esta
sesión, más de las que había registradas en el metastore en la 066).

## Restricciones respetadas

- `terraform apply` se ejecutó **acotado con `-target`** a exactamente las 30
  tablas — confirmado con `terraform plan -target=...` antes y después: "0 to add,
  30 to change, 0 to destroy" y luego "No changes.", sin ningún recurso de
  `lambda.tf`/Kafka de por medio.
- No se ha ejecutado `terraform destroy`.
- No se ha tocado `infra/terraform/lambda.tf` ni ningún fichero de
  `procesamiento/silver_gold/`.
- No se ha reabierto la decisión de usar Partition Projection frente a `MSCK
  REPAIR` periódico (ya tomada en la tarea 066, aplicada tal cual aquí).
- Las dos excepciones (`aemet_prevision_gold` con `municipio_code`,
  `cams_calidad_aire_gold` con `pollutant`) se documentan como excepciones reales
  del patrón general, no se han forzado a encajar como claves de fecha.
- `backend.hcl` (copia local de `backend.hcl.example`) y los artefactos de
  `terraform init`/`plan` (`.terraform/`, `.terraform.lock.hcl`, ficheros
  `.tfplan`) se eliminan al terminar la sesión — no se commitea nada de esto.

## Relevante para tareas futuras

- Las particiones que quedaron registradas en el metastore de Glue por los `MSCK
  REPAIR TABLE` manuales de la tarea 066 (6 tablas) ya no tienen ningún efecto: con
  projection activado Athena no las consulta. No hace falta ni conviene limpiarlas
  a mano (no hacen daño), pero tampoco hay que confundirlas con "las particiones
  reales de la tabla" si alguien inspecciona el metastore directamente (p. ej. con
  `aws glue get-partitions`) — para saber qué hay realmente disponible hay que
  mirar S3 o confiar en el rango de `projection.<clave>.range`, no el metastore.
- El rango `2026-08-01,NOW+1DAY` es fijo en el código (no depende de la fecha de
  aplicación) — no hace falta tocarlo nunca salvo que se quiera acotar el
  histórico consultable por Athena (irrelevante para el coste: Athena solo escanea
  las rutas S3 que realmente tengan objetos, un rango de fechas amplio sin datos no
  cuesta nada extra).
- Sigue pendiente (fuera de esta tarea) la deriva ya documentada del zip de
  `procesamiento/` en `aws_s3_object.procesamiento_source` frente al código de
  `main` (tareas 065/066) y los dos bugs de datasets con Silver vacío (tarea 063:
  `cartelera_cines_estrenos_silver_to_gold`, `afluencia_lugares_silver_to_gold` sin
  `--extra-py-files`) — ninguno de los dos bloquea Partition Projection en sí (una
  tabla con Silver vacío simplemente sigue devolviendo 0 filas sin error, igual que
  ya confirmó la tarea 066), pero conviene resolverlos antes de considerar el
  pipeline Silver/Gold completo end-to-end.
