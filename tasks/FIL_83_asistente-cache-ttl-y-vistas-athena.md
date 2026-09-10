---
kind: fil
title: "Asistente: caché TTL en las rutas calientes + vistas Athena para los joins repetidos"
owner: Filippos (interactive)
status: pending
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
4. **`_recent_date_filter()`** configurable (`ASSISTANT_DATE_WINDOW_DAYS`,
   por defecto 14) — para poder ampliarlo mientras el pipeline siga
   congelado sin recompilar.

## Verificación

- `asistente/tests/test_cache.py`: 2.ª llamada no invoca la función real,
  expira tras `ttl`, `ttl=0` desactiva, la clave distingue argumentos.
- Bench antes/después (script en `scratchpad`, no versionado): p50 de
  `/contexto-urbano` y `/calidad-aire` en llamadas repetidas.
- Suite `asistente/` verde; sin cambios de contrato de las tools.
