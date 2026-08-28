# FIL-03 / FIL-04 / FIL-05 — Desplegar los 3 productores de la tarea 090

## Contexto

`emt_incidencias`, `parques_jardines` y `ser_calles` existían solo como
"muestra commiteada" (tarea 090). FIL_02 les añadió `lambda_handler` +
`BronzeWriter`. FIL_03/04/05 los ponen en producción.

## Alcance de esta pasada: capa de Ingesta (Bronze), aplicada de verdad

**Decisión (28/8):** desplegar los tres como Lambda + EventBridge Scheduler
→ Bronze, con un cambio acotado a `infra/terraform/lambda.tf`. Silver/Gold
completo (bloque por dataset en `glue.tf`) queda como trabajo de seguimiento
— el JSON de Bronze es directamente consumible (como `poi_madrid`) para el
grafo y como feature de ML; agregarlo con Glue solo hace falta si la fase de
modelado lo pide.

### `infra/terraform/lambda.tf`

3 entradas nuevas en `local.producers` + 3 en `local.schedules`. El resto de
la infra (función Lambda, log group, schedule, permisos de Bronze) se deriva
por `for_each` — no hizo falta tocar nada más. Cadencias:

| Dataset | Cadencia | memoria/timeout |
|---|---|---|
| `emt_incidencias` | `rate(30 minutes)` (feed en vivo) | 256 MB / 60 s |
| `parques_jardines` | `cron(0 5 ? * MON *)` Madrid (referencia) | 256 MB / 60 s |
| `ser_calles` | `cron(30 5 ? * MON *)` Madrid (referencia) | 512 MB / 300 s (CSV de ~15 MB, 34k tramos) |

`terraform apply` (acotado con `-target` a `aws_lambda_function.producer` /
`aws_cloudwatch_log_group.producer` / `aws_scheduler_schedule.producer` /
`aws_iam_policy.ingestion_lambda_logs`, para no aplicar Kafka):
**9 added, 15 changed, 0 destroyed** (las 14 Lambdas existentes se
"cambian" solo porque el hash del zip de código compartido cambió al añadir
los 3 handlers — el código de sus handlers no cambia).

### Verificación (28/8)

`aws lambda invoke` de cada función → `200` / sin `FunctionError`. Objetos
reales en Bronze:

| Dataset | Bronze (primera invocación real) |
|---|---|
| `emt_incidencias` | `fecha=2026-08-28/hora=15/…json`, 99 KB, ~110 incidencias |
| `parques_jardines` | `…`, 394 KB, 203 parques |
| `ser_calles` | `…`, 14.7 MB, 34.486 tramos |

## FIL_04 — parques en el grafo (código, sin infra)

- `grafo/extract.py::fetch_parques_bronze()` — lee `bronze/parques_jardines/`
  directo de S3, mismo patrón que `fetch_poi_bronze`.
- `grafo/nodos.py::lugar_from_parque_bronze` / `lugares_from_parques_bronze`
  — `id = "parques_jardines:<park_id>"`, `tipo = "parque"`, mismo contrato
  que `lugar_from_poi_bronze`.
- `grafo/cargar_grafo.py` — añadido a la unión de `lugares` (entra también al
  enriquecimiento OSM y a `UBICADO_EN` / `PROXIMO_A`).
- Tests en `grafo/tests/test_nodos.py` (usan la muestra commiteada
  `parques_jardines_madrid_sample.json`). 95 tests de `grafo/` en verde.
- Verificado contra Bronze real: `fetch_parques_bronze()` → 203 registros →
  203 `:Lugar` de tipo parque, todos con ubicación.
- Recarga de la instancia real de Neo4j ejecutada (`python -m
  grafo.cargar_grafo`) — resultado con Cypher: **[pendiente de anotar tras
  la recarga]**.

## Pendiente / seguimiento

- Silver/Gold de `emt_incidencias` y `ser_calles` (bloque `glue.tf` +
  `aggregate.py` + `ge_suite.py` + tabla Athena) — solo si la fase de ML lo
  necesita agregado.
- `ser_calles` escribe ~15 MB a Bronze cada lunes; aceptable para una carga
  de referencia semanal, revisar si crece.
- FIL_05: valoración de si `ser_calles` mejora `disponibilidad_aparcamiento`
  — la ocupación en vivo sigue necesitando el dataset "SER. Tiques de
  aparcamiento", aparte.
