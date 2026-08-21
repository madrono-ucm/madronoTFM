# 069 — Grafo: leer datos reales de Silver/Gold vía Athena

## Objetivo

La tarea 067 escribió la transformación Gold/Bronze → nodos del grafo Neo4j
(`grafo/nodos.py`/`relaciones.py`/`cypher.py`), pero recibía los registros ya
como `list[dict]` en memoria, sin leer nada real. Esta tarea añade la capa de
extracción (`grafo/extract.py`): consulta **Amazon Athena** (tareas 066/068)
para todo lo que tiene Gold, y **S3 directo** para las tres fuentes que nunca
tuvieron Silver/Gold (`barrios_distritos_madrid`, `poi_madrid`,
`crtm_red_transporte_madrid`), y alimenta con datos reales la lógica de la
tarea 067 sin modificarla.

## Qué se ha añadido

- **`grafo/extract.py`**: 11 funciones `fetch_*` (una por origen de nodo) más
  `run_athena_query()` (lanza SQL contra el workgroup
  `madrono-tfm-dev-silver-gold`, sondea `get_query_execution` con backoff
  corto y parsea `get_query_results`) y `_read_bronze_records()` (lista +
  descarga JSON de S3 con `boto3`, sin Athena). Ambas rutas aceptan un
  cliente `boto3` inyectable (`athena_client`/`s3_client`) para poder
  testear sin credenciales reales.
- **`grafo/cargar_grafo.py`**: entry point que encadena `extract.py` →
  `nodos.py`/`relaciones.py` → `cypher.py` (`cargar_grafo(loader)` +
  `main()`), listo para ejecutarse el día que exista una instancia Neo4j
  real. **No se ha ejecutado contra ninguna instancia real** (sigue
  bloqueada el alta manual de AuraDB Free, tarea 043).
- **`grafo/tests/test_extract.py`**: 15 tests nuevos (46 en total en
  `grafo/tests/`, todos en verde sin el driver `neo4j` instalado) que
  mockean `boto3` por completo (`FakeAthenaClient`/`FakeS3Client`) — sin
  conexión ni credenciales reales.
- `grafo/requirements.txt`: añadido `boto3>=1.34,<2` (ya instalado en esta
  EC2, usado por `ingesta`/`procesamiento`).
- `grafo/README.md`: sección nueva "`extract.py`: la capa de lectura real"
  con la tabla de funciones, las decisiones de diseño y los hallazgos reales
  (ver abajo); actualizados también el bloque de uso y "Relevante para
  tareas futuras".

## Decisiones de diseño

- **Athena, no releer Parquet directamente** (decisión ya fijada por el
  enunciado, no reabierta): evita duplicar la lógica de particionado que ya
  resuelve Partition Projection (tarea 068) y mantiene una única vía de
  lectura de Silver/Gold desde fuera de Glue.
- **`GROUP BY <id> ... max_by(<col>, date)` en vez del histórico completo**:
  un nodo del grafo es una entidad única y su identidad/ubicación es, en la
  práctica, constante en el tiempo (mismo criterio que ya usa
  `nodos.dedupe_nodes`); traer todo el histórico de `trafico` (cientos de
  millones de filas, tarea 068) solo para `id`/`lat`/`lon` desperdiciaría
  bytes escaneados sin necesidad. Cada consulta acota además a los últimos
  14 días (`_RECENT_WINDOW_DAYS`) con un filtro de partición, y usa
  `max_by(columna, date)` para quedarse con el valor de la fila con la fecha
  más reciente dentro de esa ventana — no un valor arbitrario.
- **`_nest_location()`**: Gold aplana la ubicación a columnas `lat`/`lon`
  (a diferencia de Silver, que la anida en un `struct location`, ver
  `infra/terraform/glue.tf`), pero `grafo.nodos._location()` espera
  `record["location"] = {"lat": ..., "lon": ...}`. Se traduce en `extract.py`
  en vez de tocar `nodos.py` (ya testado en la tarea 067, y no le
  corresponde saber de dónde vienen sus columnas).
- **`_cast_athena_value()`**: `get_query_results` de Athena devuelve siempre
  texto (`VarCharValue`), sea cual sea el tipo real de columna
  (comportamiento documentado de la API, no un bug de este módulo). Se
  convierte de vuelta a `int`/`float` según `ResultSetMetadata.ColumnInfo[]
  .Type`, imprescindible para que `lat`/`lon` lleguen a
  `grafo.cypher.Neo4jLoader` como números (el `point({...})` de Cypher que
  construye `cypher.py` los necesita numéricos).
- **No se ha modificado `nodos.py`/`relaciones.py`/`cypher.py`**: no hizo
  falta ningún cambio para conectarlos — la única fricción real encontrada
  (Gold con `lat`/`lon` planas frente al `location` anidado que espera
  `_location()`) se resuelve enteramente en la capa de extracción, sin tocar
  código ya testado.

## Verificado contra datos reales de esta cuenta (`eu-west-1`, `222234418587`)

Las 11 funciones se ejecutaron una vez contra Athena/S3 reales (con las
credenciales de esta EC2) para validar el SQL antes de darlo por bueno:

| Función | Filas reales |
|---|---|
| `fetch_estaciones_trafico` | 4678 |
| `fetch_estaciones_calidad_aire` | 23 |
| `fetch_estaciones_ruido` | 31 |
| `fetch_paradas_emt` | 1 |
| `fetch_paradas_bicimad` | 679 |
| `fetch_lugares_aparcamientos` | 0 |
| `fetch_lugares_cartelera_cines` | 0 |
| `fetch_distritos_bronze` / `fetch_barrios_bronze` / `fetch_poi_bronze` / `fetch_paradas_crtm_bronze` | 0 (las 4) |

## Tres hallazgos reales encontrados y documentados (no corregidos, fuera de alcance)

1. **`transporte_publico_emt` Gold solo tiene 1 `stop_id` distinto** en las 8
   particiones reales (`date=2026-08-14` a `2026-08-21`, ~1144 filas/día) —
   confirmado con `SELECT date, COUNT(DISTINCT stop_id) ... GROUP BY date`.
   No es un bug de la consulta; es el estado real de la ingesta de ese
   dataset a día de hoy.
2. **Gold de `aparcamientos` está completamente vacío** (0 objetos reales,
   solo un marcador `_$folder$`) — un tercer caso de Gold vacío, además de
   los dos ya conocidos desde la tarea 063 (`cartelera_cines_estrenos`/
   `afluencia_lugares`). `fetch_lugares_aparcamientos()` devuelve `[]` sin
   error, tal como exige el enunciado para este caso.
3. **Los tres orígenes Bronze-only nunca se subieron al bucket Bronze
   real.** Confirmado con `aws s3 ls s3://madrono-tfm-dev-bronze-
   222234418587/`: solo aparecen los 14 datasets con productor en bucle. Sus
   propios scripts de `ingesta/capturas/` (`barrios_distritos_madrid.py`,
   `poi_madrid.py`, `crtm_red_transporte_madrid.py`) solo escriben JSON
   local (`_write_json`) y nunca llaman a `BronzeWriter` — son cargas
   puntuales de referencia, documentadas como tales desde su propia tarea de
   captura. Los nombres de prefijo de S3 que usa `extract.py`
   (`barrios_distritos_madrid_distritos`, `barrios_distritos_madrid_barrios`,
   `poi_madrid`, `crtm_red_transporte_madrid`) son, por tanto, una
   **convención asumida** (patrón `<dataset>/fecha=/hora=/*.json` de
   `bronze.py` + nombres ya usados por las muestras commiteadas), no
   verificada contra ningún dato real porque no existe ninguno. Las cuatro
   funciones devuelven `[]` sin error, exactamente como exige el enunciado.

## Restricciones respetadas

- Solo lectura contra AWS: las 11 funciones se ejecutaron una vez para
  validar el SQL/parseo (consultas Athena y `GetObject`/`ListObjectsV2` de
  S3, todas de solo lectura) — ningún `PutObject`, ninguna escritura, ningún
  `terraform apply`.
- No se ha conectado a ninguna instancia Neo4j real (sigue sin existir).
- No se ha modificado `grafo/nodos.py`/`relaciones.py`/`cypher.py`.
- Los tres casos de lista vacía encontrados (`aparcamientos` Gold, los tres
  orígenes Bronze-only) se manejan sin excepción, tal como exigía el
  enunciado, y quedan documentados como hallazgos reales, no como bugs de
  esta tarea.

## Relevante para tareas futuras

- Con `extract.py` y `cargar_grafo.py` ya escritos, la siguiente tarea con
  una instancia Neo4j real disponible podría ejecutar la carga end-to-end
  (`python3 -m grafo.cargar_grafo`) sin más cambios en esta capa.
- Si una tarea futura decide subir las tres cargas de referencia
  (`barrios_distritos_madrid`, `poi_madrid`, `crtm_red_transporte_madrid`) al
  bucket Bronze real (añadiendo `BronzeWriter` a esos scripts), debe usar
  exactamente los cuatro nombres de dataset que ya asume `extract.py` (ver
  arriba) para que las funciones los encuentren sin cambios adicionales.
- Las 3 relaciones restantes del esquema (`UBICADO_EN`, `PROXIMO_A`,
  `CONECTADO_CON`, ver tarea 067) van a necesitar su propia extracción real
  — reutilizable desde este mismo `grafo/extract.py` (p. ej. `PROXIMO_A`
  puede construirse directamente sobre las ubicaciones que ya devuelven las
  funciones `fetch_*` existentes).
- El hallazgo de `aparcamientos` Gold vacío (mismo patrón que los dos ya
  conocidos desde la tarea 063) debería investigarse junto con aquellos dos
  antes de considerar el pipeline de `aparcamientos` completo end-to-end.
