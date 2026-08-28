# FIL-06 — `afluencia_lugares`: retirar Google Maps, señal derivada como Gold

## Parte 1/2 — retirar el productor Google Popular Times (HECHO, 28/8)

`afluencia_lugares` dependía al 100% de Google Popular Times. Coste 0
imposible (tarea 083); la Lambda programada fallaba en cada ejecución por
falta de `GOOGLE_MAPS_API_KEY`; el Gold estaba a **0 filas** y las Lambda/Glue
"tenían éxito" con entrada mock, ocultando el hueco.

- `infra/terraform/lambda.tf`: quitadas las entradas de `afluencia_lugares`
  de `local.producers` / `local.schedules` y `GOOGLE_MAPS_API_KEY` de
  `local.secrets`. `terraform apply -target`: **0 added, 17 changed, 4
  destroyed** (función Lambda + log group + schedule + parámetro SSM
  placeholder).
- `ingesta/requirements.txt`: quitado `populartimes @ git+...`.
- `ingesta/capturas/afluencia_lugares_madrid.py`: banner RETIRADO; se
  conserva como referencia del esquema (la memoria §6.8 documenta por qué se
  evaluó y descartó esta vía).
- La Lambda Layer aún contiene `populartimes` (inofensivo, sin consumidor).
  Se limpiará en la próxima reconstrucción de la layer por otro motivo.

## Fórmula compartida (HECHO)

`procesamiento/silver_gold/afluencia_lugares/nivel.py` — extrae la fórmula de
`nivel_estimado` de `asistente/mcp_agent/tools.py` (tarea 089) a un módulo
puro y testado (`tests/test_nivel.py`, 7 tests), para que la compartan la
tool del asistente (en vivo) y el job por lotes (Gold). Hoy la copia sigue
duplicada en `tools.py` con una nota; el refactor de `tools.py` para importar
de `nivel.py` queda pendiente (evita tocar ese módulo ya testado en la misma
pasada).

## Parte 2/2 — el job por lotes (HECHO, 28/8)

Tabla Gold `afluencia_lugares_por_lugar_fecha_hora` refrescada **cada hora**
(trigger `aws_glue_trigger.afluencia_lugares_estimada`, `cron(20 * * * ? *)`
UTC), una fila por `:Lugar`: `nivel_estimado` + los valores de sensor de los
que sale + `data_completeness` (0..4). Sin ninguna dependencia de Google.

### Qué se construyó

- `procesamiento/silver_gold/afluencia_lugares/estimada.py` (puro, testado):
  `sensores_por_tipo()` agrupa los `PROXIMO_A` del grafo por tipo quitando el
  prefijo `<fuente>:`; `fila_gold()` construye la fila (usa `nivel.py`).
- `procesamiento/silver_gold/afluencia_lugares/glue_estimada.py`: job de Glue.
  SSM → Neo4j (una consulta: `:Lugar` + sus sensores `PROXIMO_A`) → lee la
  **hora más reciente** de la partición de hoy de las 4 tablas Gold de
  sensores (Spark) → `fila_gold` por lugar → Parquet particionado por
  `date` + `hora` (zero-pad `"17"`), `overwrite` dinámico = re-ejecución
  idempotente.
- `infra/terraform/glue.tf`:
  - `aws_s3_object.glue_script_afluencia_lugares_silver_to_gold` repuntado a
    `glue_estimada.py`; el job `afluencia_lugares_silver_to_gold` (mismo
    recurso/nombre, sin destroy) con `--additional-python-modules
    "neo4j==5.28.1"` (¡sin coma! Glue separa por comas, `neo4j>=5,<6` falla)
    + los args `--neo4j_*_param` y `--*_gold_path`.
  - IAM (`glue_afluencia_lugares_data_access`): `ssm:GetParameter` sobre
    `.../secrets/neo4j-*` + `kms:Decrypt` acotado por `kms:ViaService`;
    `s3:GetObject` sobre las 4 tablas Gold de sensores; `s3:DeleteObject`
    sobre el prefijo Gold propio (overwrite dinámico).
  - `aws_glue_catalog_table.afluencia_lugares_gold`: esquema nuevo (columnas
    `lugar_id`/`tipo`/`nivel_estimado`/`n_*`/`avg_*`/`data_completeness`),
    partición `date` + `hora`, `projection.hora` `digits = "2"`.
  - `afluencia_lugares_bronze_to_silver` queda como job muerto (sin trigger).
- `infra/terraform/glue_scheduling.tf`: `afluencia_lugares` sale de
  `glue_trigger_daily_datasets` (destruye sus 2 triggers diarios) y gana el
  trigger `SCHEDULED` horario propio.

### Verificación (28/8)

`aws glue start-job-run` → **SUCCEEDED** (~80 s). Athena:
`SELECT nivel_estimado, count(*) FROM afluencia_lugares_por_lugar_fecha_hora
GROUP BY 1` → **534 `bajo`, 7 `medio`, 45 `sin_datos`** (586 `:Lugar` en
total). Ejemplo real: `poi_madrid:69452` → `bajo`, con 8 estaciones de
tráfico + 4 de BiciMAD + 1 de calidad del aire cerca (`data_completeness = 3`).
`n_ruido` casi siempre 0 (Gold de ruido aún muy escaso, pocas estaciones).

Tres iteraciones hasta el verde: (1) `neo4j>=5,<6` con coma → el instalador
de módulos de Glue lo parte en dos; (2) `createDataFrame` sin esquema
explícito falla si una columna sale entera a `None`; (3) filtro `hour ==
hora` exacto → la hora en curso aún no está en Gold, se cambió a "hora
máxima disponible del día" (mismo criterio que `asistente/tools.py`).

### Diseño original (referencia)

Un **Glue job** (reutiliza el recurso `aws_glue_job.afluencia_lugares_
silver_to_gold` ya existente de la tarea 060, repuntando su script):

1. `--additional-python-modules "neo4j>=5,<6"` (mismo mecanismo que
   `great_expectations` en el resto de jobs); credenciales Neo4j de SSM vía
   `boto3` (`/madrono-tfm/dev/secrets/neo4j-*`, ver `infra/OPERACION.md`).
2. Lista `:Lugar` (id, tipo, lat, lon) y, por lugar, corre las 4 consultas
   `PROXIMO_A` de `asistente/neo4j_client.py` (tráfico / ruido /
   calidad_aire / BiciMAD dentro de 300 m) — portar los strings Cypher, son
   cortos y estables.
3. Lee el último valor Gold de cada sensor encontrado (Spark leyendo el
   Parquet de `gold/<tabla>/`, o Athena): `avg_service_level` /
   `avg_occupancy_ratio` (tráfico), `avg_laeq_db` (ruido),
   `avg_occupancy_ratio` (BiciMAD), `avg_value` (calidad_aire, solo
   trazabilidad).
4. `nivel_estimado(...)` de `nivel.py` con las listas de valores.
5. Escribe Parquet a `gold/afluencia_lugares_por_lugar_fecha_hora/
   date=YYYY-MM-DD/` con columnas: `lugar_id, tipo, lat, lon, hora,
   nivel_estimado, n_trafico, n_ruido, n_bicimad, n_calidad_aire,
   avg_service_level, avg_laeq_db, avg_bicimad_occ, avg_aqi_value,
   data_completeness` (0-4 señales / 4), `processed_at`.
6. Trigger: pasa de `CONDITIONAL` (esperaba a `bronze-to-silver`) a
   `SCHEDULED` horario en `glue_scheduling.tf`. El job `bronze-to-silver` de
   este dataset se elimina (ya no hay Bronze).
7. `athena.tf`: la tabla de projection de `afluencia_lugares_por_lugar_
   fecha_hora` ya existe; ampliar `projection.date.range` si sigue estrecho
   (arrancar `2026-08-01`, ver tarea 098).

### Aceptación

- `SELECT count(distinct lugar_id), max(processed_at) FROM
  afluencia_lugares_por_lugar_fecha_hora` devuelve ~todos los `:Lugar` y un
  timestamp fresco.
- Sin ninguna referencia a `populartimes` / `GOOGLE_MAPS_API_KEY` en
  `ingesta/` / `infra/` / requirements (hecho en la parte 1).
- Las filas se acumulan hora a hora.

### Dependencia

Necesita el grafo con buena cobertura de `:Lugar` (parques incluidos, FIL_04)
y con las relaciones `PROXIMO_A` de esos nodos cargadas — ver el problema de
recarga de abajo.

## Problema abierto: recarga de Neo4j poco fiable

Los 203 nodos `:Lugar {tipo:"parque"}` (FIL_04) **sí están** en la instancia
real, pero `cargar_grafo.py` ha muerto dos veces seguidas con
`neo4j.exceptions.SessionExpired` (~8-13 min) durante la fase de relaciones
— AuraDB Free corta la conexión en recargas largas de escritura secuencial
(la recarga de 51 min del 28/8 fue suerte). Los `PROXIMO_A` de los parques
quedan sin crear.

**Ticket de seguimiento sugerido**: hacer `cargar_grafo.py` resiliente
(reconexión/reintento por lote, o `UNWIND` para agrupar los `MERGE` y bajar
la recarga de ~50 min a minutos). Hasta entonces, reintentar la recarga, o
un script acotado que solo cree las relaciones de los nodos nuevos.
