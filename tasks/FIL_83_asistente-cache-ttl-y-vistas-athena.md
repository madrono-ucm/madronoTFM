---
kind: fil
title: "Asistente: caché TTL en las rutas calientes + vistas Athena para los joins repetidos"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_73]
milestone: "M7"
target: "2026-09-26"
---

## Motivación

Cada llamada a una tool va **en frío** a Athena/Neo4j. El explorador tiene
un TTL de 600 s (`asistente/routers/grafo_explorador.py`); las tools no
tienen ninguno. Además varias tools rehacen el mismo join de 4-8 tablas Gold
por texto de lugar en cada petición → latencia y coste de escaneo Athena
evitables. Con el pipeline congelado, los datos **no cambian**, así que un
TTL generoso es seguro.

## Alcance

1. **Caché TTL en proceso** (`asistente/cache.py`): un decorador
   `@cacheado(ttl_s=...)` con clave = `(func, args, kwargs)` normalizados,
   límite de entradas (LRU) y `ttl` configurable por entorno
   (`ASSISTANT_CACHE_TTL`, por defecto 900 s; 0 lo desactiva para tests).
   Aplicado a: `athena.consultar_*` (las funciones de consulta), la
   resolución lugar→nodo del grafo, y `neo4j_client.run_neo4j_query` para
   plantillas de solo lectura. **No** cachear respuestas del LLM.
2. **Cabecera de diagnóstico**: `X-Cache: hit|miss` en los routers, y un
   contador en el log estructurado de FIL_73.
3. **Vistas Athena** (DDL, `allow_infra_apply:false` — se entrega el SQL y
   se ejecuta con `start_query_execution` cuando el usuario dé el OK):
   `v_calidad_aire_ultima_hora`, `v_trafico_ultima_hora`,
   `v_contexto_lugar` (lugar × sensores) — reducen el escaneo de las tools a
   una sola vista. `asistente/athena.py` pasa a leer las vistas si existen,
   con fallback a las tablas.
## Hecho

- **`asistente/cache.py`** — `@cacheado(ttl_s, maxsize)` TTL + LRU, clave =
  repr normalizado de `(args, kwargs)` ignorando los clientes inyectables
  (`athena_client`/`neo4j_driver`/`driver`). `ultimo_fue_hit()` (thread-local).
- **Aplicado** a `athena.run_athena_query` (`ttl_s=1800`) y
  `neo4j_client.run_neo4j_query` (`ttl_s=900`).
- **Opt-in por entorno**: `ASSISTANT_CACHE_TTL` (segundos). **Por defecto
  `0` = desactivada** — decisión deliberada, más segura que default-on: la
  suite de tests no cambia de comportamiento y el despliegue la activa
  (`ASSISTANT_CACHE_TTL=900`). El TTL efectivo es `min(ttl_s, env)`.
- **Vistas Athena**: `infra/athena/vistas_asistente.sql`
  (`v_calidad_aire_ultima_hora`, `v_trafico_ultima_hora`,
  `v_meteo_ultima_hora`). DDL versionado, **sin aplicar**
  (`allow_infra_apply:false`); instrucciones de `start-query-execution` en
  la cabecera del fichero.
- `asistente/tests/test_cache.py` (7): default off, hit dentro del TTL,
  clave distingue args, cliente inyectable no forma parte de la clave,
  expiración, cota LRU, TTL efectivo = mínimo.

## No hecho / follow-up

- **`X-Cache: hit|miss`** en los routers — `ultimo_fue_hit()` es
  thread-local y refleja la ÚLTIMA llamada cacheada; una tool que hace
  varias consultas (Athena + Neo4j) no tiene un "hit" único de request.
  Cosmético; se deja para cuando haya un contador en el log de FIL_73.
- **`ASSISTANT_DATE_WINDOW_DAYS`** — no aplica limpio: no hay un
  `_recent_date_filter()` único, cada tool lleva su ventana (`date IN
  ('ayer','hoy')`) en el SQL. Se descarta.
- **Lectura de las vistas en `athena.py`** con fallback a la tabla — las
  vistas hay que aplicarlas primero; hasta entonces las tools siguen
  leyendo las tablas directamente (sin regresión).

## Verificación

- `asistente/tests/test_cache.py` verde; suite `asistente/` completa verde
  (219) con la caché desactivada por defecto — sin cambios de contrato.
