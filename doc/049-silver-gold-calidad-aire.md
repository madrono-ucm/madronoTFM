# 049 — Silver/Gold: calidad del aire (quinto dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/calidad_aire/`, replicando el patrón que la
tarea 041 fijó con tráfico y que las tareas 046/047/048 ya replicaron con
transporte público EMT, BiciMAD y aparcamientos rotacionales (ver
`procesamiento/README.md`): `transform.py` (Bronze→Silver, puerta de
calidad, Python puro), `aggregate.py` (Silver→Gold, Python puro, fuente de
verdad documental/de test), `ge_suite.py` (Great Expectations, requiere
`pyspark`/GX) y `glue_bronze_to_silver.py`/`glue_silver_to_gold.py` (entry
points reales de Glue). Fuente: `ingesta/capturas/calidad_aire_madrid.py`
(lecturas horarias de la red de 24 estaciones de calidad del aire de
Madrid, ver doc/006). **Alcance: solo este dataset y solo
código/infraestructura, sin `terraform apply`** — mismo criterio que las
tareas 041/046/047/048, el resto de subpaquetes de `silver_gold/` no se ha
tocado.

## Sin `geo.py` (como en `transporte_publico_emt`/`bicimad`/`aparcamientos`)

`ingesta/capturas/calidad_aire_madrid.py` (`normalize_record`) ya entrega
`location.lat`/`location.lon` en WGS84 (coordenadas del CSV de metadatos de
estaciones `212629-0-estaciones-control-aire`), no hace falta ninguna
reproyección — confirmado por el propio enunciado de la tarea.

## Confirmado: las lecturas no válidas (`V01`..`V24` == `"N"`) ya se filtran en `ingesta/`

El enunciado pedía confirmar si `ingesta/` ya excluye las lecturas horarias
marcadas como no válidas por la fuente antes de llegar a Bronze. Se
confirmó leyendo `calidad_aire_madrid.py`: `normalize_record` usa
`_latest_valid_hour`, que solo considera horas con código `"V"` en
`V01`..`V24` y descarta el registro entero (ni siquiera llega a Bronze, la
función devuelve `None`) si el registro estación+magnitud+día no tiene
ninguna lectura válida ese día. El esquema Bronze de este dataset, por
tanto, no contiene ningún campo `V01`..`V24` — solo el `value` de la última
lectura válida. `transform.validate_record` no repite ese filtro (no
podría: el campo no existe en Bronze); esto se documenta explícitamente en
el docstring de `transform.py` para que no parezca una omisión frente al
resto del patrón.

## Diferencia real frente al resto del patrón: rango plausible por contaminante

A diferencia de tráfico/BiciMAD/aparcamientos (magnitudes homogéneas por
dataset), cada lectura de `calidad_aire` va etiquetada con un contaminante
(`pollutant`, la abreviatura del Anexo II del PDF "Intérprete de ficheros de
calidad del aire" que también usa `ingesta/capturas/calidad_aire_madrid.py`
— `"NO2"`, `"PM10"`, `"O3"`, etc.) con su propia unidad y escala típica. Un
único rango de plausibilidad para todos los registros no distinguiría un
NO2 corrupto de un CO válido (escalas y unidades distintas: µg/m³ frente a
mg/m³, y órdenes de magnitud distintos incluso dentro de µg/m³).

`transform.PLAUSIBLE_MAX_BY_POLLUTANT` da una cota superior laxa por cada
uno de los 18 contaminantes que puede devolver el feed en tiempo real
(mismo conjunto que `MAGNITUDES` en `ingesta/capturas/calidad_aire_madrid.py`),
tomando como referencia orientativa los umbrales de alerta legales de la UE
(SO2: 500, NO2: 400, O3: 240 µg/m³) donde existen, y una cota igualmente
laxa (varios órdenes de magnitud por encima de cualquier episodio de
contaminación real observado en Madrid) para el resto — deliberadamente no
son límites legales de calidad del aire (que son medias en ventanas de
tiempo largas: 1h/8h/24h/anual, no un tope instantáneo), solo pensados para
atrapar valores claramente corruptos sin descartar picos de contaminación
real. Un contaminante que no aparezca en la tabla (no debería ocurrir) no se
rechaza por rango, solo se exige que no sea negativo — mismo criterio de
"ausente/desconocido se acepta" que ya usaba el resto del patrón para campos
opcionales.

## Puerta de calidad (`transform.validate_record`)

- `station_id`/`pollutant` (`magnitude_abbr`)/`measured_at`/`value` no
  nulos (los cuatro campos clave que pedía el enunciado).
- `measured_at`/`ingested_at` parseables y timezone-aware (mismo criterio
  que el resto del patrón).
- `value` no negativo, y por debajo de `PLAUSIBLE_MAX_BY_POLLUTANT[pollutant]`
  cuando ese contaminante está en la tabla.

## Agregación Silver → Gold (`aggregate.py`)

Por **`(station_id, pollutant, fecha, hora)`** — no solo por estación y
hora: una misma estación reporta varios contaminantes simultáneamente, cada
uno con su propia unidad y escala, así que mezclarlos en un único agregado
por estación+hora produciría una media sin significado (promediar un NO2 y
un CO en la misma fila). El contaminante es, junto con la estación y la
hora, parte de la clave natural de agregación — es el único dataset del
patrón donde la clave de agregación tiene tres componentes de identidad
(además de fecha/hora) en vez de dos. Cada fila agrega `samples_count`,
`avg`/`max`/`min_value`, `first`/`last_measured_at` y conserva
`unit`/`pollutant_name`/`magnitude_code` (constantes en la práctica) más
`lat`/`lon` (una estación tiene ubicación fija).

## `ge_suite.py`: rango por contaminante sin expectation nativa

Great Expectations no tiene una expectation de "el máximo depende del valor
de otra columna". Se resuelve igual que la consistencia de contadores de
`bicimad`/`aparcamientos`: una columna auxiliar
(`value_over_plausible_max`) calculada en `glue_bronze_to_silver.py` —
traduce `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión
`when/otherwise` de Spark, en vez de repetir la tabla como una segunda
fuente de verdad — y comprobada con GX como `<= 0`.

## Tests

22 tests nuevos en `procesamiento/tests/` (`test_calidad_aire_transform.py`,
`test_calidad_aire_aggregate.py`), más un fixture de 10 registros
(`tests/fixtures/calidad_aire_bronze_sample.json`: las 5 lecturas reales de
`ingesta/capturas/samples/calidad_aire_madrid_sample.json` — 2 estaciones,
4 contaminantes distintos, NOx/NO/NO2/O3 — + 5 que violan cada regla de
rechazo por turnos: `station_id` nulo, contaminante nulo, `measured_at`
corrupto, `value` nulo, valor de NO2 muy por encima de su rango plausible).
Un test específico (`test_same_value_is_accepted_for_a_pollutant_with_a_higher_plausible_range`)
verifica que el mismo valor numérico se acepta o rechaza según el
contaminante, confirmando que el rango es por contaminante y no global.
Suite completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) +
118 de `procesamiento` (27 de tráfico + 20 de transporte público EMT + 23 de
BiciMAD + 23 de aparcamientos + 22 nuevos de calidad del aire),
`python3 -m unittest discover -s procesamiento/tests -t .` y
`-s ingesta/tests -t .`.

Igual que en las tareas 041/046/047/048, `ge_suite.py` y los dos
`glue_*.py` de este dataset importan `pyspark`/`great_expectations`/
`awsglue` a nivel de módulo y **no se han podido importar ni ejecutar en
esta sesión** (mismo motivo: disco compartido muy limitado en esta EC2) —
ningún test los importa a propósito
(`procesamiento/silver_gold/calidad_aire/__init__.py` solo expone
`transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_calidad_aire`, acotado por prefijo `bronze/calidad_aire/*` ·
`silver/calidad_aire/*` ·
`gold/calidad_aire_por_estacion_contaminante_hora/*`, más el catálogo de
sus dos tablas Silver/Gold; dos `aws_glue_job`, Bronze→Silver y
Silver→Gold), **sin tocar** los bloques de tráfico, transporte público EMT,
BiciMAD ni aparcamientos, ni compartir su rol IAM (mismo principio de
mínimo privilegio por dataset). `data.archive_file.procesamiento_source` no
necesitó ningún cambio: ya empaquetaba todo `procesamiento/` (salvo
`tests/`), así que el subpaquete nuevo se incluye automáticamente en el
artefacto de librería compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real. `.terraform/`, `.terraform.lock.hcl` y
el directorio `build/` generados por `terraform init`/`validate` se
eliminaron al terminar — nada de esto se commitea.

## `procesamiento/README.md`: actualizado para reflejar el quinto dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los cinco datasets. Se
añadió una sección "Quinto dataset: `calidad_aire`" con el razonamiento
completo del rango de plausibilidad por contaminante y la confirmación del
filtro de lecturas no válidas.

## Restricciones respetadas

- Alcance limitado a `calidad_aire` — no se ha tocado
  `procesamiento/silver_gold/trafico/`,
  `procesamiento/silver_gold/transporte_publico_emt/`,
  `procesamiento/silver_gold/bicimad/` ni
  `procesamiento/silver_gold/aparcamientos/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/calidad_aire_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado cuatro veces
  (041→046→047→048→049): un subpaquete `silver_gold/<dataset>/` con
  `transform.py`/`aggregate.py` (Python puro, testable)/`ge_suite.py`/
  `glue_*.py`, más `geo.py` **solo si la fuente lo necesita** (ninguno de
  los cuatro últimos datasets lo tiene), más un bloque en `glue.tf` con su
  propio rol IAM.
- `calidad_aire` es el primer dataset del patrón donde un solo campo
  numérico (`value`) representa magnitudes de escala distinta según otro
  campo del mismo registro (`pollutant`) — el criterio a replicar si una
  tarea futura añade un dataset con la misma forma es
  `transform.PLAUSIBLE_MAX_BY_POLLUTANT`: una tabla `dict[etiqueta, rango]`
  en `transform.py`, con una etiqueta ausente de la tabla aceptada por
  defecto (no rechazada por rango, solo por negatividad si aplica) en vez
  de fallar o inventar un rango. La misma tabla se reutiliza en
  `ge_suite.py`/`glue_bronze_to_silver.py` (traducida a una expresión
  `when/otherwise` de Spark), no se repite como constante independiente.
- Antes de aplicar cualquiera de los cinco bloques de infraestructura de
  Glue: smoke-test de los cinco `ge_suite.py` en un Glue Studio Notebook
  real (el de `calidad_aire`, como los de `bicimad`/`aparcamientos`,
  necesita además confirmar en el runtime real que su columna auxiliar
  funciona como se espera, al no existir una expectation nativa de "el
  máximo depende del valor de otra columna"), y revisar si
  `great_expectations==0.18.19` sigue siendo la versión adecuada en el
  momento de aplicar (misma pendiente que dejaron las tareas
  041/046/047/048, ahora aplica a cinco datasets).
- `PLAUSIBLE_MAX_BY_POLLUTANT` usa umbrales de alerta legales de la UE como
  referencia orientativa donde existen (SO2, NO2, O3), no como límite
  regulatorio real (que son medias en ventanas de tiempo, no topes
  instantáneos) — si una tarea futura necesita comparar contra los límites
  legales reales de calidad del aire (p.ej. para un indicador de
  cumplimiento normativo), esa lógica pertenece a una agregación adicional
  sobre Gold (medias en ventanas de 8h/24h/anuales), no a esta puerta de
  calidad de Silver, que solo atrapa valores instantáneos corruptos.
