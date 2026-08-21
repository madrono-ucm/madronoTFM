---
id: 69
slug: grafo-lectura-real-athena
title: 'Grafo: leer datos reales de Silver/Gold vía Athena'
status: in_progress
force: true
allow_infra_apply: false
branch: task/069-grafo-lectura-real-athena
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-21T09:30:00+00:00'
updated_at: '2026-08-21T20:28:04.015714+00:00'
started_at: '2026-08-21T20:28:04.015691+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 067 escribió `grafo/nodos.py`/`relaciones.py` (Python puro,
testado con fixtures) pero recibe los registros ya como `list[dict]` en
memoria — no lee nada real todavía. La tarea 066 desplegó Athena sobre el
catálogo de Silver/Gold, y la 068 arregló el descubrimiento de particiones
(Partition Projection) para que las consultas devuelvan datos reales sin
`MSCK REPAIR TABLE` manual. Esta tarea conecta ambas piezas: añade la capa
de extracción que consulta Athena de verdad y alimenta la lógica ya escrita
en 067.

**Decisión ya tomada (no la reabras)**: leer vía **Athena** (consultas SQL,
`boto3` + `start_query_execution`/`get_query_results`, mismo patrón que ya
usó la tarea 066 para verificar), no releer los ficheros Parquet
directamente con `pyarrow`/`pandas` — evita duplicar lógica de particionado
y mantiene una única vía de lectura para todo lo que consuma Silver/Gold
desde fuera de Glue.

## Objetivo

Añadir `grafo/extract.py`: funciones que consultan Athena (una consulta por
tipo de nodo: estaciones de tráfico/calidad del aire/ruido desde Gold,
paradas EMT/BiciMAD desde Gold, aparcamientos/cines desde Gold) y devuelven
`list[dict]` en el formato que ya esperan `nodos.py`/`relaciones.py` de la
tarea 067 — sin modificar esa lógica ya testada.

## Alcance concreto

1. `grafo/extract.py`: una función por fuente (p.ej.
   `fetch_estaciones_trafico()`, `fetch_paradas_emt()`...) que construye la
   consulta SQL (agrupando por identidad única del punto/estación/parada —
   `SELECT DISTINCT` o `GROUP BY` sobre el `id` correspondiente, no traigas
   el histórico completo de cada uno, solo la ubicación/identidad más
   reciente), la lanza con `boto3` contra el workgroup
   `madrono-tfm-dev-silver-gold` (tarea 066), espera el resultado
   (`get_query_execution` en bucle con backoff corto, mismo patrón que
   `doc/066-consulta-athena-silver-gold.md` documentó) y parsea
   `get_query_results` a `list[dict]`.
   Para las fuentes que siguen siendo solo Bronze
   (`barrios_distritos_madrid`, `poi_madrid`, `crtm_red_transporte_madrid`
   — nunca tuvieron Silver/Gold), lee directamente el JSON de S3 con
   `boto3` (sin Athena, no hay tabla de catálogo para ellas) — mismo
   `bucket`/prefijo que usa `ingesta/capturas/bronze.py`.
2. Tests en `grafo/tests/test_extract.py`: mockea `boto3` (respuestas de
   Athena) para probar el parseo sin conexión real — sigue el mismo
   criterio que el resto de `grafo/tests/`, no dependas de credenciales AWS
   reales para que los tests pasen.
3. Un script/entry point (`grafo/cargar_grafo.py` o similar) que encadena
   `extract.py` → `nodos.py`/`relaciones.py` → `cypher.py`, listo para
   ejecutarse el día que exista una instancia Neo4j real — pero **no lo
   ejecutes contra ninguna instancia real** (sigue sin existir, ver tarea
   043).
4. Actualiza `grafo/README.md` con esta pieza nueva.

## Restricciones

- NO modifiques `grafo/nodos.py`/`relaciones.py`/`cypher.py` salvo que
  encuentres un error real al conectarlos — si lo haces, documenta por qué.
- NO ejecutes ningún comando `aws` con efectos reales de escritura — esta
  tarea es de solo lectura contra Athena/S3 (las consultas Athena en sí
  tienen coste de escaneo, pero son lecturas, no cambian nada).
- NO conectes a ninguna instancia real de Neo4j.
- Si al ejecutar `grafo/extract.py` contra Athena real encuentras que
  alguna tabla sigue sin datos (los dos datasets con Silver vacío,
  `cartelera_cines_estrenos`/`afluencia_lugares`, ver tareas 061/066), no es
  un bug de esta tarea — maneja el caso de lista vacía sin error y
  documéntalo.

## Criterios de aceptación

- `grafo/extract.py` consulta Athena/S3 real y devuelve datos reales (no
  fixtures) en el formato esperado por `nodos.py`/`relaciones.py`.
- Tests de `extract.py` en verde sin conexión real (mockeados).
- `grafo/README.md` actualizado.
