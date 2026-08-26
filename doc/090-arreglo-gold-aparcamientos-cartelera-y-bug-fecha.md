# 090 — Prioridad 2 de NEXT_STEPS.md: `aparcamientos` (ya resuelto), `cartelera_cines_estrenos` (sesiones + bug real) y el mismo bug en otros 2 datasets

## Contexto

Sesión interactiva (no `madrono-agent`) para atacar la Prioridad 2 de
`NEXT_STEPS.md`: dos tablas Gold rotas, `aparcamientos` (`doc/052`, 0 filas
escritas sin diagnosticar) y `cartelera_cines_estrenos` (`doc/063`,
`AnalysisException`, Silver vacío). Verificado todo contra AWS real
(cuenta `222234418587`, región `eu-west-1`, perfil `madrono`) — Athena real,
`aws glue start-job-run` real, `aws lambda invoke` real. Ningún test se dio
por bueno solo con fixtures locales cuando había una alternativa de
verificarlo en vivo.

## `aparcamientos`: ya estaba resuelto, `NEXT_STEPS.md` estaba desactualizado

El bug de `doc/052` (Gold vacío tras `.where(fecha != "__sin_medida__")`
sobre una lectura completa de Silver) ya no existe en el código actual:
`procesamiento/silver_gold/aparcamientos/glue_silver_to_gold.py` fue
reescrito por las tareas 072/075 (lectura incremental, una única partición
`fecha=/hora=` por ejecución, recalculando `fecha`/`hora` desde
`measured_at`) — efecto colateral no documentado de ese trabajo. Verificado
con Athena real: `aparcamientos_por_parking_hora` tiene 601 filas/día
reales y consistentes (ocupación, lat/lon) desde varios días atrás hasta
hoy (2026-08-26). No ha hecho falta ningún cambio de código; solo se
actualiza `NEXT_STEPS.md`.

## `cartelera_cines_estrenos`: causa raíz más profunda que "Silver vacío"

`doc/063` diagnosticó `AnalysisException: Unable to infer schema` al leer
un Silver sin ningún objeto. Ese síntoma concreto ya no existe (las tareas
072/075/076 añadieron `partition_has_objects` antes de cualquier
`spark.read.parquet`), pero el dataset seguía sin producir Gold. Causa real
verificada en vivo: el único escritor programado de Bronze
(`lambda_handler` → `sweep_premieres`) solo produce registros
`record_type == "estreno_semana"` (título + fecha de estreno, sin cine ni
horario) — la puerta de calidad de Silver
(`procesamiento/silver_gold/cartelera_cines_estrenos/transform.py`) los
rechaza siempre con `"not_a_screening_session"`, exactamente como ya
advertía el docstring de ese módulo desde la tarea 055. Confirmado con el
informe real de Great Expectations del 2026-08-25
(`_quality_reports/cartelera_cines_estrenos/..._20260825T081641.json`):
`element_count: 0` en las 5 expectations. No es un bug de
`procesamiento/` — es la ausencia de un segundo modo de captura
(`fetch_cinema_showtimes`, que ya existía en el código pero sin ningún
handler/schedule).

### Arreglo: `sweep_showtimes` + `event.tipo` en el mismo Lambda (mismo patrón que AEMET)

`ingesta/capturas/cartelera_cines_madrid.py`:

- `sweep_showtimes(config, captured_at)`: recorre `config.cinema_ids`
  (`DEFAULT_CINEMA_IDS` por defecto, un cine por cadena — mismo alcance
  moderado que el resto del módulo frente a los términos de uso de
  SensaCine) llamando a `fetch_cinema_showtimes` por cine.
- `lambda_handler` decide `sweep_premieres` (`tipo="estrenos"`, por
  defecto) o `sweep_showtimes` (`tipo="sesiones"`) según `event.get("tipo")`
  — mismo patrón exacto que `aemet_prevision_avisos.py` (un único
  Lambda/schedule Terraform, `input.tipo` distinto).

`infra/terraform/lambda.tf`: nueva entrada en `local.schedules`,
`cartelera_cines_estrenos_sesiones` (`cron(0 7 * * ? *)` Europe/Madrid,
`input = {tipo = "sesiones"}`), una hora antes del schedule de estrenos
para que la mayoría de sesiones del día sigan siendo futuras cuando la
puerta de calidad las evalúe (`showtime_already_passed`). Mismo Lambda que
ya existía, sin recursos nuevos de IAM/logs (reutiliza
`aws_iam_role.ingestion`, que ya tenía `s3:PutObject` de alcance
`${bronze_bucket}/*`, no acotado por dataset).

**Aplicado de verdad**: `terraform apply` acotado con `-target` a
`aws_lambda_function.producer["cartelera_cines_estrenos"]` +
`aws_scheduler_schedule.producer["cartelera_cines_estrenos_sesiones"]`
(`-var lambda_dependencies_layer_arn=...:1` explícito — sin él, Terraform
intentaba **quitar** la layer de dependencias ya adjunta a esta función en
producción, arn:...:layer:madrono-tfm-dev-ingesta-dependencies:1, drift no
relacionado con esta tarea; habría roto `import bs4` en la próxima
invocación real). Verificado con `aws lambda invoke` real: `tipo=sesiones`
escribió 52 registros de sesión reales (ambas cadenas, horarios futuros);
`tipo` por defecto (`estrenos`) se probó después del despliegue y sigue
funcionando igual que antes.

### Bug real encontrado en la propia verificación: `Column 'fecha' does not exist`

Al lanzar `cartelera_cines_estrenos_silver_to_gold` de verdad contra el
Silver recién generado, falló con `AnalysisException: Column 'fecha' does
not exist`. Causa: la lectura incremental de la tarea 076 acota
`spark.read.parquet(...)` a una única partición `fecha=<fecha>/` — con eso,
Spark deja de exponer `fecha` como columna (queda fija en la propia ruta
leída, solo `hora=` sigue siendo un nivel real de subdirectorio bajo esa
ruta), pero el `groupBy(...)`/`withColumnRenamed("fecha", ...)` del job
seguía asumiendo que `fecha` era una columna real — mismo motivo por el que
`aparcamientos_silver_to_gold.py` ya recalculaba sus columnas de partición
tras la tarea 072, solo que aquí nadie lo había hecho. Arreglo: añadir
`.withColumn("fecha", F.lit(fecha))` justo después de leer, con el valor
Python ya conocido (`fecha = today(processed_at)`), antes de cualquier
`groupBy`.

### El mismo bug, encontrado además en otros 2 jobs (uno de ellos rompiendo producción en directo)

Antes de dar por cerrada la verificación, se revisaron los 6
`glue_silver_to_gold.py` que usan `daily_partition_uri` (tarea 076) y
referencian `"fecha"` en su `groupBy` sin recalcularla. `aemet_prevision_
avisos`/`afluencia_lugares`/`cams_calidad_aire` ya la recalculan
explícitamente (`withColumn`) — no tienen el bug. Los otros 2 sí:

| Dataset | Estado real en producción antes del arreglo | Verificado |
|---|---|---|
| `agenda_eventos` | **Fallando en directo los 4 días previos** (2026-08-23 a 08-26, mismo `AnalysisException`; el último éxito fue 08-22) | Relanzado tras el arreglo: `SUCCEEDED`, filas reales nuevas en Gold para `date=2026-08-26` (verificado con `aws s3 ls`, timestamp fresco) |
| `bluesky_menciones` | Fallando de forma intermitente (08-23 y 08-24 `FAILED`; 08-22/25/26 `SUCCEEDED` solo porque `partition_has_objects` cortó antes de llegar al `groupBy`, sin Silver nuevo esos días) | Relanzado tras el arreglo: `SUCCEEDED`. No se pudo verificar con una fila fresca del `groupBy` corregido porque Silver no tenía datos nuevos hoy (2026-08-26) — no hay dato real que forzar sin inventarlo |
| `aforos_peatones_bicicletas` | Bug presente pero **nunca disparado** en producción: la fuente está descontinuada desde 2024-06-30 (tarea 087/089), así que `partition_has_objects` nunca deja pasar ninguna ejecución real hasta el `groupBy` | Corregido por consistencia con el resto del patrón; no verificable en vivo hasta que la fuente vuelva a publicar (o mediante un backfill dedicado, fuera de alcance) |

Los 3 arreglos son idénticos: `.withColumn("fecha", F.lit(fecha))` tras el
`spark.read.parquet(...)`, mismo patrón que `cartelera_cines_estrenos`.

## Despliegue de los 4 scripts corregidos: bypass deliberado de Terraform

Los 4 `glue_silver_to_gold.py` corregidos se despliegan como objetos S3
individuales (`aws_s3_object.glue_script_<dataset>_silver_to_gold`,
`script_location` de cada `aws_glue_job`), con clave nombrada por hash del
contenido — al cambiar el contenido, Terraform quiere reemplazar la clave.
**Descubierto al planificar**: los 4 jobs también dependen de
`--extra-py-files` → `aws_s3_object.procesamiento_source`, un único zip
**compartido por prácticamente todos los jobs Glue del proyecto** (~40
referencias en `glue.tf`, bronze→silver y silver→gold de los 14 datasets).
Como ese zip empaqueta el árbol completo de `procesamiento/` (incluye,
sin usarlos como import, los propios scripts driver que se acaban de
editar), su contenido también cambia y Terraform lo marca para
reemplazo — y un `-target` que incluya los 4 `aws_glue_job` arrastra ese
reemplazo como dependencia real, no como efecto secundario evitable.

Aplicar ese plan tal cual habría **borrado la clave S3 vieja del zip
compartido** mientras los ~10 datasets restantes (no tocados por este
`-target`) seguirían con su `--extra-py-files` ya desplegado apuntando a
esa clave vieja en AWS — su próxima ejecución habría fallado con
`NoSuchKey` al arrancar. Se abortó ese plan sin aplicarlo.

**En su lugar**: se sobrescribió el contenido de los 4 objetos S3 de script
*en el sitio* (misma clave ya usada por el `script_location` real de cada
job, vía `s3.put_object` directo, sin tocar `procesamiento_source` ni
ningún argumento de ningún job). Esto es intencionadamente **drift de
Terraform** respecto al nombre de clave que el código querría generar
(mismo patrón de drift ya documentado y aceptado en `doc/087`/Prioridad 1
de `NEXT_STEPS.md`) — el contenido desplegado ya es el correcto (verificado
en vivo, ver arriba), pero un `terraform plan` sin acotar seguirá
mostrando estos 4 objetos (+ el zip compartido) como pendientes de
reemplazo hasta que la Prioridad 1 (reconciliación completa) los absorba
en una pasada que sí actualice también los ~10 datasets restantes que
comparten el zip.

## Restricciones respetadas

- `terraform apply` real solo para el Lambda/schedule de `cartelera_cines_
  estrenos` (2 recursos), acotado con `-target`; ningún otro recurso
  tocado por Terraform.
- El resto del arreglo (4 scripts Glue) se desplegó fuera de Terraform,
  deliberadamente, para no arrastrar el zip compartido y no romper los
  demás jobs — ver sección anterior.
- No se ha tocado `infra/terraform/glue.tf` de partition projection (tarea
  087, todavía sin aplicar) ni ningún recurso de Kafka/Lambda ajeno a esta
  tarea.
- `backend.hcl`/`.terraform`/`build/` locales, creados solo para
  `plan`/`apply`, borrados al terminar.
- Ningún cambio irreversible en AWS: solo escritura de datos reales (que
  es justamente el objetivo del dataset) y despliegue de código ya
  probado con 46+ tests unitarios en verde antes de tocar AWS.

## Relevante para tareas futuras

- **Prioridad 1 de `NEXT_STEPS.md`** ahora también cubre: 4 objetos
  `aws_s3_object.glue_script_*_silver_to_gold` + el zip compartido
  `aws_s3_object.procesamiento_source`, con drift deliberado de esta
  tarea. La reconciliación completa (aplicar sin `-target`) los alineará
  sin riesgo, porque ya no quedan jobs con `--extra-py-files` apuntando a
  una clave que fuera a desaparecer sin remplazo.
- El patrón "`daily_partition_uri` + `groupBy` sobre `fecha` sin
  recalcularla" es la fragilidad real a vigilar en cualquier dataset nuevo
  de cadencia diaria que se añada al patrón de la tarea 076: si el job lee
  una única partición `fecha=<fecha>/`, `fecha` deja de ser una columna
  real y hay que reintroducirla con `F.lit(fecha)` (o equivalente) antes
  de cualquier `groupBy`/referencia — `aemet_prevision_avisos`/
  `afluencia_lugares`/`cams_calidad_aire` ya lo hacían bien; ahora los 7 lo
  hacen.
- `disponibilidad_aparcamiento` (Prioridad 4, tool del asistente) ya no
  está bloqueada por Gold de `aparcamientos` — tiene datos reales y
  frescos desde antes de esta tarea.
