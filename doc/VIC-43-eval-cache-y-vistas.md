# VIC_43 — QA de la caché TTL del asistente + vistas Athena (FIL_83, 2026-09-10)

Verificación de `asistente/cache.py` (`@cacheado`), su aplicación a
`athena.run_athena_query`/`neo4j_client.run_neo4j_query`, y el DDL de
vistas Athena de `infra/athena/vistas_asistente.sql`. Antes de evaluar, se
leyó `tasks/FIL_83_asistente-cache-ttl-y-vistas-athena.md` completo: su
propia sección "No hecho / follow-up" ya declara sin construir 3 de las
piezas que este ticket pedía verificar (cabecera `X-Cache`, `_recent_date_
filter()` configurable, lectura de vistas con fallback) — no son huecos
ocultos, están documentados como descartados/diferidos por el propio autor.

## 1. Corrección de la caché — ✅ correcto

`asistente/tests/test_cache.py` (7 tests, todos verdes) ya cubre: caché
desactivada por defecto, hit dentro del TTL, la clave distingue argumentos,
el cliente inyectable (`athena_client`/`neo4j_driver`/`driver`) no forma
parte de la clave, expiración real, cota LRU, y que el TTL efectivo es
`min(ttl_s, ASSISTANT_CACHE_TTL)`. Revisado el código de `_clave()` y
`wrapper()`: `threading.Lock` protege lectura+escritura del `OrderedDict`,
`move_to_end` mantiene el orden LRU correcto en hit y en inserción.

## 2. Qué NO se cachea / normalización de `momento` — ✅ correcto, mejor de lo que pedía el ticket

`chat.py` no importa `asistente.cache` ni usa `@cacheado` en ningún punto
(confirmado por grep) — el único "cacheado" que menciona su docstring es un
memoizado ad-hoc de `_tools_schema` (el esquema estático de las tools, no
una respuesta del LLM), sin relación con `asistente.cache`.

Sobre "la clave debería normalizar `momento` a la hora, no al segundo": la
premisa del ticket asume que `momento` es un argumento directo de las
funciones cacheadas. No lo es — `run_athena_query(sql, database, ...)` y
`run_neo4j_query(query, params, ...)` cachean sobre el **texto ya
construido** de la consulta. Trazado en `tools.py::_calidad_aire_impl`:
`momento` se convierte a `fecha = instante.date().isoformat()` y se
interpola directamente en el SQL (`WHERE date = '{fecha}'`); la hora nunca
llega al SQL, se filtra después en Python sobre las filas del día completo.
Efecto: la clave de caché normaliza a **día**, no a hora — más agresivo de
lo que pedía el punto 2, y correcto dado que el pipeline lleva congelado
desde el 30/8 (un día entero es, hoy, un dato inmutable). Para
`run_neo4j_query`, los `params` de las plantillas de resolución espacial no
incluyen `momento` en absoluto (son consultas estructurales, no
temporales), así que no aplica.

## 3. LRU sin cota — ✅ correcto

`test_lru_cota` fuerza 5 inserciones sobre `maxsize=3` y confirma
`cache_len() <= 3`. Revisado el código: `popitem(last=False)` expulsa
siempre el menos recientemente usado, no el más antiguo por inserción
(`move_to_end` se llama tanto en hit como en insert).

## 4. Cabecera `X-Cache: hit/miss` — ⚠️ no implementada (ya declarado, no oculto)

`ultimo_fue_hit()` solo se llama desde `asistente/cache.py` (su propia
definición) y desde `asistente/tests/test_cache.py`. **Cero** routers la
usan — no hay ninguna cabecera `X-Cache` en ninguna respuesta HTTP hoy.
`FIL_83` ya lo documenta en su sección "No hecho": es "cosmético" y queda
pendiente de un contador en el log estructurado (`FIL_73`) porque
`ultimo_fue_hit()` es thread-local y refleja solo la ÚLTIMA llamada
cacheada — una tool que hace varias consultas (Athena + Neo4j) no tiene un
único "hit" de request, hace falta diseñar qué significa la cabecera antes
de cablearla. No se abre ticket nuevo: ya está correctamente registrado
como pendiente en `FIL_83`.

## 5. Vistas Athena — ⚠️ DDL versionado pero sin aplicar ni leído (ya declarado)

`infra/athena/vistas_asistente.sql` existe, está commiteado
(`2656ed2`) y define `v_calidad_aire_ultima_hora`, `v_trafico_ultima_hora`,
`v_meteo_ultima_hora` con el patrón "última fila por partición compuesta"
(`max(date || lpad(hour,2))` + join). No hay ninguna referencia a estos
nombres de vista en `asistente/athena.py` ni en `asistente/mcp_agent/
tools.py` — las tools siguen leyendo las tablas base directamente, sin
fallback que probar todavía porque no hay nada que hacer *fallback desde*.
Correcto según lo que `FIL_83` declaró: las vistas necesitan aplicarse a
mano primero (`allow_infra_apply:false`). Único hallazgo nuevo de este
punto: **el DDL no estaba documentado en `infra/OPERACION.md`** — corregido
en este ticket (sección nueva, con el comando de aplicación).

## 6. Contrato: misma respuesta con caché on/off — ✅ correcto, test nuevo añadido

No existía ningún test que comparase explícitamente la respuesta de una
`tool` real con la caché activada y desactivada. Añadido
`asistente/tests/test_cache_paridad.py`
(`test_misma_respuesta_con_cache_desactivada_y_activada`): llama a
`tools._calidad_aire_impl` con `ASSISTANT_CACHE_TTL` sin definir, luego con
`900` (miss + hit), y compara los tres resultados con `assertEqual` — son
idénticos. 8/8 tests verdes (7 de `test_cache.py` + 1 nuevo).

## 7. Suite completa con la caché activada — ❌ bug real confirmado y arreglado

**Hallazgo real, no solo teórico.** Con `ASSISTANT_CACHE_TTL=900` puesto
para la suite `asistente/` **completa**, **17 tests fallan**
(`test_mcp_tools.py`, `test_opciones_movilidad.py`, `test_afluencia_
estimada.py`, `test_consulta_grafo.py`) — todos pasan de forma aislada.
Causa raíz confirmada: `run_athena_query`/`run_neo4j_query` cachean por
texto de consulta; dos tests distintos que generan el **mismo** SQL/Cypher
pero inyectan un `FakeAthenaClient`/`FakeNeo4jDriver` con datos **distintos**
comparten la misma entrada de caché (el cliente inyectable se excluye de la
clave a propósito, ver punto 2) — un test posterior lee la respuesta
*fake* de un test anterior. Ejemplo reproducido:
`EventosCercanosToolTests::test_eventos_se_ordenan_por_distancia_ascendente`
espera `["Cercano", "Lejano"]` y recibe `[]` (la lista vacía cacheada de
otro caso con la misma consulta Neo4j). En producción esto no es un riesgo
—solo hay un cliente Athena/Neo4j real por proceso, con datos que no
cambian dentro del TTL por diseño— pero la suite **no era segura** de
ejecutar con `ASSISTANT_CACHE_TTL` a un valor real, que es exactamente el
valor de despliegue (`infra/OPERACION.md`, `900`).

**Arreglado y confirmado**: `asistente/tests/conftest.py` nuevo, con un
fixture `autouse=True` que limpia ambas cachés (`cache_clear()`) antes y
después de cada test. Reejecutada la suite completa con
`ASSISTANT_CACHE_TTL=900`: **226 passed, 57 subtests passed** (el +1 sobre
los 225 de antes es `test_cache_paridad.py`) — los 17 fallos desaparecen
por completo. No hizo falta abrir un `FIL_*` de seguimiento.

## Criterios de aceptación del ticket

- `test_cache.py` verde (7/7) + `test_misma_respuesta_con_cache_desactivada_y_activada` (nuevo) verde → ✅.
- Suite `asistente/` completa verde con `ASSISTANT_CACHE_TTL` por defecto (225 tests + 57 subtests) y con `=0` explícito (mismo resultado) → ✅, verificado dos veces.
- Suite `asistente/` completa verde con `ASSISTANT_CACHE_TTL=900` (el valor real de despliegue) → inicialmente ❌ 17 tests rotos (hueco real: sin reset de caché entre tests); ✅ arreglado con `conftest.py` y reconfirmado verde (226 + 57 subtests).
- DDL de vistas versionado → ✅ ya lo estaba; documentado en `infra/OPERACION.md` → ✅ añadido en este ticket.
