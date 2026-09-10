---
kind: vic-eval
title: "QA — caché TTL del asistente + vistas Athena (FIL_83): corrección, invalidación, sin cambio de contrato"
owner: Claude (QA)
status: done
depends_on: [FIL_83]
created_at: "2026-09-10"
---

## Contexto

FIL_83 añade `asistente/cache.py` (`@cacheado(ttl_s)`) sobre las rutas
calientes + DDL de vistas Athena + `_recent_date_filter()` configurable.

## Alcance — verificación

1. **Corrección de la caché**: 2.ª llamada con los mismos args no ejecuta la
   función real (spy); la clave distingue args/kwargs (incluido `momento`);
   `ttl` expira; `ASSISTANT_CACHE_TTL=0` la desactiva por completo (para los
   tests deterministas del resto de la suite).
2. **Qué NO se cachea**: respuestas del LLM (`chat.py`), nada con
   `momento=None` que dependa de "ahora" sin cuantizar la hora — verificar
   que la clave normaliza `momento` a la hora, no al segundo.
3. **LRU/límite**: no crece sin cota; entradas viejas se expulsan.
4. **Cabecera `X-Cache`**: `hit`/`miss` correcta en los routers tocados;
   contador en el log estructurado (FIL_73) sin PII.
5. **Vistas Athena**: el SQL de `v_*` está en el repo (no solo aplicado a
   mano); `asistente/athena.py` usa la vista si existe y cae a la tabla si
   no (test con ambas ramas, mockeado).
6. **Sin cambio de contrato**: las respuestas de las tools son idénticas con
   caché on/off (mismo JSON) — test de igualdad.
7. **Suite entera**: con la caché activada por defecto, ¿algún test se
   vuelve flaky por estado compartido entre casos? Debe haber un `reset` en
   el `setUp`/fixture.

## Criterios de aceptación

- `test_cache.py` verde + test de "misma respuesta con/sin caché".
- Suite `asistente/` completa verde con `ASSISTANT_CACHE_TTL` por defecto y
  con `=0`.
- DDL de vistas versionado y documentado en `infra/OPERACION.md`.

## Hecho (2026-09-10, Claude QA)

Los 7 puntos verificados contra el código real de `FIL_83` (cuya propia
sección "No hecho" ya declaraba sin construir la cabecera `X-Cache`, el
`_recent_date_filter()` configurable y la lectura de vistas con fallback —
no son huecos ocultos). Detalle completo, punto a punto, en
[`doc/VIC-43-eval-cache-y-vistas.md`](../doc/VIC-43-eval-cache-y-vistas.md).

**Hallazgo real (no solo teórico)**: con `ASSISTANT_CACHE_TTL=900` (el
valor real de despliegue) puesto para la suite `asistente/` completa,
**17 tests fallaban** por contaminación cruzada de la caché entre tests
que generan el mismo SQL/Cypher con datos *fake* distintos (el cliente
inyectable se excluye de la clave a propósito). Arreglado con
`asistente/tests/conftest.py` (fixture `autouse` que limpia ambas cachés
antes/después de cada test) — reconfirmado verde: 226 tests + 57 subtests,
tanto con la caché desactivada como con `900`.

**Añadido**: `asistente/tests/test_cache_paridad.py` (contrato: misma
respuesta de una tool real con caché on/off) y una sección nueva en
`infra/OPERACION.md` documentando el DDL de `infra/athena/
vistas_asistente.sql` (versionado pero sin aplicar).

Ningún `FIL_*` nuevo — el único bug real encontrado (punto 7) se arregló
directamente, es de higiene de tests, no de comportamiento en producción.
