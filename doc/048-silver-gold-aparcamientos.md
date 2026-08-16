# 048 — Silver/Gold: aparcamientos rotacionales (cuarto dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/aparcamientos/`, replicando el patrón que la
tarea 041 fijó con tráfico y que las tareas 046/047 ya replicaron con
transporte público EMT y BiciMAD (ver `procesamiento/README.md`):
`transform.py` (Bronze→Silver, puerta de calidad, Python puro),
`aggregate.py` (Silver→Gold, Python puro, fuente de verdad documental/de
test), `ge_suite.py` (Great Expectations, requiere `pyspark`/GX) y
`glue_bronze_to_silver.py`/`glue_silver_to_gold.py` (entry points reales de
Glue). Fuente: `ingesta/capturas/aparcamientos_madrid.py` (ocupación de
aparcamientos públicos rotacionales de Madrid vía el servicio SOAP de
datos.madrid.es, ver doc/005). **Alcance: solo este dataset y solo
código/infraestructura, sin `terraform apply`** — mismo criterio que las
tareas 041/046/047, el resto de subpaquetes de `silver_gold/` no se ha
tocado.

## Sin `geo.py` (como en `transporte_publico_emt`/`bicimad`)

`ingesta/capturas/aparcamientos_madrid.py` (`normalize_record`) ya entrega
`location.lat`/`location.lon` en WGS84 (coordenadas del propio servicio
SOAP `GetListParking`), no hace falta ninguna reproyección.

## Decisión explícita del enunciado: ocupación no compartida NO se descarta

Compartir la ocupación en tiempo real es voluntario para cada aparcamiento
(ver doc/005): `measured_at`, `free_spaces` y `total_spaces` pueden venir a
`null` de forma independiente entre sí en un mismo registro Bronze (el
listado `GetListParking` puede no traer el nodo de ocupación, y la llamada
aparte `GetDetailParking` para las plazas totales puede fallar
independientemente). Se decidió que estos registros **sí pasan a Silver**
con los campos numéricos a `null`, en vez de descartarse:

- Un aparcamiento sin ocupación compartida en un instante dado sigue siendo
  un aparcamiento real (nombre, dirección, ubicación) — descartarlo
  perdería esa información sin necesidad.
- Descartarlos silenciosamente ocultaría que la cobertura de datos en
  tiempo real de este dataset es parcial por diseño de la fuente, no un
  fallo de captura.

`transform.validate_record` solo rechaza combinaciones imposibles/corruptas
(no ausencia de dato): `free_spaces`/`total_spaces` negativos, o
`free_spaces > total_spaces` cuando ambos están presentes. `to_silver_record`
calcula `occupancy_ratio` = `free_spaces / total_spaces` cuando ambos están
disponibles, `null` en caso contrario.

Esta decisión se propaga a `aggregate.py`: los registros sin `measured_at`
(sin instante de medida) se excluyen de la agregación horaria de Gold (no
hay hora a la que asignarlos), pero permanecen en Silver para auditoría de
cobertura. A diferencia de `transporte_publico_emt` (que usa `ingested_at`
como sustituto exacto de `measured_at`, al no existir ningún concepto de
"instante de medida" en esa fuente), aquí **no** se usa `ingested_at` como
sustituto: sí existe un instante de medida real cuando la fuente lo
comparte, y aproximarlo por la hora de captura introduciría un desfase
innecesario.

## Agregación Silver → Gold (`aggregate.py`)

Por `(parking_id, fecha, hora)` — un aparcamiento, como una estación de
BiciMAD, tiene ubicación fija, así que Gold sí incluye `lat`/`lon`. Cada
fila agrega `samples_count`, `avg_free_spaces`, `avg_occupancy_ratio` (media
del ratio solo sobre las muestras donde ambos operandos estaban
disponibles) y `total_spaces` (primer valor no nulo observado, capacidad
constante en la práctica).

## `glue_bronze_to_silver.py`: partición `fecha=__sin_medida__`

Detalle específico de este dataset: como `measured_at` puede ser `null`,
esas filas se particionan bajo `fecha=__sin_medida__/hora=__sin_medida__`
en vez de perderse (siguen siendo consultables para auditoría de
cobertura). `glue_silver_to_gold.py` filtra esa partición antes de agregar,
igual que `aggregate.py` excluye esos registros de la agregación horaria.
La columna auxiliar de consistencia para `ge_suite.py`
(`free_spaces_over_total_spaces`, ya que GX no tiene una expectation nativa
de "columna <= columna") usa `coalesce(..., 1_000_000_000)` para el
`total_spaces` ausente, de forma que un registro con cualquiera de los dos
operandos a `null` nunca viole la regla — igual que hace
`validate_record` (solo compara cuando ambos están presentes).

## Tests

23 tests nuevos en `procesamiento/tests/` (`test_aparcamientos_transform.py`,
`test_aparcamientos_aggregate.py`), más un fixture de 10 registros
(`tests/fixtures/aparcamientos_bronze_sample.json`: los 5 aparcamientos
reales de `ingesta/capturas/samples/aparcamientos_madrid_sample.json` + 1
con ocupación no compartida en tiempo real (`measured_at`/`free_spaces`/
`total_spaces` a `null`, válido — pasa la puerta de calidad) + 4 que violan
cada regla de rechazo por turnos: `parking_id` nulo, plazas libres
negativas, plazas totales negativas, libres por encima de totales). Suite
completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) + 96 de
`procesamiento` (27 de tráfico + 20 de transporte público EMT + 23 de
BiciMAD + 23 nuevos de aparcamientos), `python3 -m unittest discover -s
procesamiento/tests -t .` y `-s ingesta/tests -t .`.

Igual que en las tareas 041/046/047, `ge_suite.py` y los dos `glue_*.py` de
este dataset importan `pyspark`/`great_expectations`/`awsglue` a nivel de
módulo y **no se han podido importar ni ejecutar en esta sesión** (mismo
motivo: disco compartido muy limitado en esta EC2) — ningún test los
importa a propósito
(`procesamiento/silver_gold/aparcamientos/__init__.py` solo expone
`transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_aparcamientos`, acotado por prefijo `bronze/aparcamientos/*` ·
`silver/aparcamientos/*` · `gold/aparcamientos_por_parking_hora/*`, más el
catálogo de sus dos tablas Silver/Gold; dos `aws_glue_job`, Bronze→Silver y
Silver→Gold), **sin tocar** los bloques de tráfico, transporte público EMT
ni BiciMAD, ni compartir su rol IAM (mismo principio de mínimo privilegio
por dataset). `data.archive_file.procesamiento_source` no necesitó ningún
cambio: ya empaquetaba todo `procesamiento/` (salvo `tests/`), así que el
subpaquete nuevo se incluye automáticamente en el artefacto de librería
compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real.

## `procesamiento/README.md`: actualizado para reflejar el cuarto dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los cuatro datasets. Se
añadió una sección "Cuarto dataset: `aparcamientos`" con el razonamiento
completo de la decisión de ocupación no disponible.

## Restricciones respetadas

- Alcance limitado a `aparcamientos` — no se ha tocado
  `procesamiento/silver_gold/trafico/`,
  `procesamiento/silver_gold/transporte_publico_emt/` ni
  `procesamiento/silver_gold/bicimad/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/aparcamientos_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado cuatro veces
  (041→046→047→048): un subpaquete `silver_gold/<dataset>/` con
  `transform.py`/`aggregate.py` (Python puro, testable)/`ge_suite.py`/
  `glue_*.py`, más `geo.py` **solo si la fuente lo necesita** (ninguno de
  los tres últimos datasets lo tiene), más un bloque en `glue.tf` con su
  propio rol IAM.
- `aparcamientos` es el primer dataset del patrón donde Silver admite
  registros con campos numéricos a `null` a propósito (ver arriba) — si una
  tarea futura añade un quinto dataset con la misma característica (fuente
  donde compartir parte de los datos es opcional), el criterio a replicar
  es este: admitir el registro parcial en Silver, calcular las magnitudes
  derivadas como `null` cuando falte cualquier operando, y excluir esos
  registros solo de la agregación horaria de Gold (no del propio Silver)
  cuando no tengan un instante de medida.
- Antes de aplicar cualquiera de los cuatro bloques de infraestructura de
  Glue: smoke-test de los cuatro `ge_suite.py` en un Glue Studio Notebook
  real (el de `aparcamientos`, como el de `bicimad`, necesita además
  confirmar en el runtime real que su columna auxiliar de consistencia
  funciona como se espera, al no existir una expectation nativa de
  "columna <= columna"), y revisar si `great_expectations==0.18.19` sigue
  siendo la versión adecuada en el momento de aplicar (misma pendiente que
  dejaron las tareas 041/046/047, ahora aplica a cuatro datasets).
- Si una tarea futura quisiera medir explícitamente la cobertura de
  aparcamientos que comparten ocupación en tiempo real (cuántos de los ~75
  del listado real, ver `ingesta/capturas/aparcamientos_madrid.py`), la
  partición `fecha=__sin_medida__` de Silver ya es la fuente natural para
  esa métrica, sin necesidad de releer Bronze.
- La ubicación de cada aparcamiento en Silver/Gold ya es su ubicación real y
  fija (a diferencia de `transporte_publico_emt`, donde `location` es la
  posición de un autobús en movimiento) — si una tarea futura necesita esta
  ubicación para el grafo Neo4j (tarea 043), no hace falta ninguna fuente
  adicional.
