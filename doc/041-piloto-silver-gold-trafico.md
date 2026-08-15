# 041 — Piloto Bronze→Silver→Gold de tráfico (Glue + Great Expectations)

## Qué se implementó

Primer piloto de la fase 2 del proyecto (limpieza/normalización Bronze→Silver y
agregación Silver→Gold, ver memoria del TFM, apartados 5.5/6.2-6.4), acotado a un
único dataset (`trafico`, el más maduro de `ingesta/`) para establecer el patrón
antes de extenderlo al resto de fuentes. **Alcance de esta tarea: solo código e
infraestructura, sin aplicar nada en AWS** — mismo patrón que la tarea 001 con el
lakehouse.

Directorio nuevo `procesamiento/` (análogo de `ingesta/` para esta fase), ver
`procesamiento/README.md` para el diseño completo. Resumen de las decisiones
clave:

- **Motor**: AWS Glue (Spark serverless), no un clúster EMR persistente — mismo
  principio de coste mínimo que Lambda + EventBridge Scheduler en `ingesta/`.
- **Lógica de negocio en Python puro** (`geo.py`, `transform.py`, `aggregate.py`,
  solo `stdlib`), separada de los entry points reales de Glue
  (`glue_bronze_to_silver.py`, `glue_silver_to_gold.py`, que sí requieren
  `pyspark`). Esto es lo que permite tener tests unitarios reales en esta EC2 de
  desarrollo, que no tiene Spark ni Great Expectations instalados (disco muy
  limitado, compartido con el pipeline — se ha descartado instalarlos aquí por
  riesgo de agotarlo).
- **Reproyección EPSG:25830→WGS84 sin `pyproj`**: fórmulas cerradas de Snyder
  implementadas en Python puro (`procesamiento/silver_gold/trafico/geo.py`),
  verificadas con una prueba de round-trip (proyectar un punto conocido de Madrid
  y recuperarlo con la inversa, error < 1e-8°) y contra la coordenada real de
  doc/002. Evita añadir una dependencia nativa compilada (mismo tipo de fricción
  de despliegue que causó `netCDF4` en su día, doc/019/032).
- **Puerta de calidad**: `transform.validate_record` (Python puro, testeado) es
  quien decide qué registros llegan a Silver (rangos de intensidad/ocupación/
  carga/nivel de servicio, bounding box de Madrid tras reproyectar, sensores con
  error descartados). **Great Expectations corre dentro del mismo job de Glue**
  (no como job/paso separado), **después** de ese filtro, como capa de
  observabilidad/auditoría: valida el Silver ya filtrado y escribe un informe
  JSON versionado junto a la partición correspondiente. Cada expectation de GX
  (`ge_suite.py`) está anotada con la regla de `validate_record` que reproduce —
  la misma regla expresada dos veces a propósito (una testable sin GX, otra
  declarativa con informe), no dos fuentes de verdad independientes. Justificación
  completa en el docstring de `ge_suite.py` y en `procesamiento/README.md`.
- **Agregación Gold**: por `(point_id, fecha, hora)`, no por distrito — cruzar con
  `barrios_distritos_madrid` exigiría resolver qué distrito contiene cada punto
  (point-in-polygon), justo el tipo de relación espacial que modelará la tarea 043
  (grafo Neo4j); anticiparlo aquí con una heurística ad-hoc duplicaría ese trabajo
  con peor información.

## Tests

27 tests nuevos (`procesamiento/tests/`, `python3 -m unittest discover -s
procesamiento/tests -t .`), todos en verde, sin dependencias nuevas:

- `test_geo.py`: round-trip de la reproyección + verificación contra la
  coordenada real de doc/002 + casos de bounding box.
- `test_transform.py`: cada regla de la puerta de calidad por separado +
  normalización (reproyección, ratios) + un fixture de 10 registros Bronze
  (`tests/fixtures/trafico_bronze_sample.json`, 5 válidos + 5 que violan cada
  regla por turnos) verificando el split completo válidos/rechazados.
- `test_aggregate.py`: agrupación por punto/hora, medias/máximos/mínimos,
  bucket de una sola muestra, registros sin `measured_at` ignorados.

La suite completa del proyecto (`ingesta/tests` + `procesamiento/tests`) sigue en
verde: 258 tests de `ingesta` (sin cambios) + 27 nuevos de `procesamiento`.

`ge_suite.py` y los dos `glue_*.py` (requieren `pyspark`/`great_expectations`/
`awsglue` a nivel de import) **no se han podido importar ni ejecutar** en esta
sesión por la misma razón de disco — ningún test los importa a propósito
(`procesamiento/silver_gold/trafico/__init__.py` solo expone `geo`/`transform`/
`aggregate`). Están escritos con cuidado sobre la API pública documentada de
Glue/GX, pero sin verificación de ejecución real; antes del primer despliegue
conviene una prueba de humo en un notebook/endpoint de desarrollo de Glue (ver
`procesamiento/README.md`, "Qué no se ha podido ejecutar en este entorno").

## Terraform (`infra/terraform/glue.tf`, nuevo)

Sin aplicar. `aws_glue_job` × 2 (Bronze→Silver, Silver→Gold, jobs separados para
poder reintentar cada etapa de forma independiente), `aws_iam_role.glue_trafico`
con la política gestionada `AWSGlueServiceRole` + una política propia acotada por
prefijo (bronze/trafico/\*, silver/trafico/\*, gold/trafico_por_punto_hora/\*,
más el catálogo de las dos tablas de este dataset — ni un permiso más),
`aws_glue_catalog_database`/`table` para Silver/Gold (Bronze no se cataloga: son
lotes JSON crudos sin esquema único garantizado entre los 21 productores). El
script y la librería común (`procesamiento/`, empaquetado con
`data.archive_file`, mismo patrón que `ingesta_source` de la tarea 029) se suben
al bucket de artefactos ya existente de la tarea 032
(`aws_s3_bucket.build_artifacts`), reutilizado en vez de crear un bucket nuevo
solo para esto. Great Expectations se instala en tiempo de job vía el parámetro
nativo `--additional-python-modules` de Glue (paquete puro de PyPI, sin necesidad
de una Lambda Layer/CodeBuild a medida).

`terraform validate` limpio, verificado en esta tarea con
`terraform init -backend=false` (sin backend real, sin credenciales AWS). No se
ha ejecutado `terraform plan`/`apply` contra la cuenta real — eso es una tarea
posterior con revisión de plan de por medio, mismo patrón que las tareas 014/015.

## `ingesta/README.md`: pequeña actualización de contexto

La sección de `trafico_madrid.py` decía que la reproyección a WGS84 "queda como
posible mejora futura si una tarea de Silver/Gold la necesita" — se ha
actualizado para apuntar a esta tarea (`procesamiento/silver_gold/trafico/geo.py`),
sin tocar ningún código de `ingesta/` (Bronze sigue sin reproyectar a propósito:
conserva los datos tal como llegan de la fuente).

## Restricciones respetadas

- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales — solo código e infraestructura sin aplicar, tal como pedía el
  enunciado (sin `allow_infra_apply`).
- No se ha procesado ningún dato real de Bronze: toda la verificación usa el
  fixture de ejemplo (`procesamiento/tests/fixtures/trafico_bronze_sample.json`).
- Alcance limitado a un único dataset (tráfico) — no se ha tocado ningún otro
  productor ni se ha intentado generalizar el patrón a las demás fuentes.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2 (riesgo de
  disco compartido con el pipeline) — la lógica de negocio se probó en Python
  puro, y las partes que sí requieren esas dependencias quedan documentadas como
  no verificadas por ejecución real en este entorno.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- Patrón a reutilizar al extender esto a más fuentes: un subpaquete
  `silver_gold/<dataset>/` con `transform.py`/`aggregate.py` (Python puro,
  testable) + `ge_suite.py` (GX, ejecutado en Glue) + `glue_*.py` (entry points),
  más un bloque en `glue.tf` con su propio rol IAM acotado por prefijo (no
  compartido entre datasets).
- Antes de aplicar esta infraestructura: smoke-test de `ge_suite.py` en un Glue
  Studio Notebook real, y revisar si `great_expectations==0.18.19`
  (`var.great_expectations_pip_spec`) sigue siendo la versión adecuada en el
  momento de aplicar.
- La agregación por distrito (en vez de por punto de medida) queda
  deliberadamente pendiente de la tarea 043 (grafo Neo4j) — ver
  `procesamiento/README.md`, sección "Transformación Silver → Gold".
- `intensity_ratio` (intensidad/intensidad de saturación) es la magnitud más
  reutilizable como "nivel de congestión" normalizado si una tarea futura
  necesita comparar tráfico con otros datasets de movilidad (BiciMAD, EMT).
