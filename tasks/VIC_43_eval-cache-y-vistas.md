---
kind: vic-eval
title: "QA — caché TTL del asistente + vistas Athena (FIL_83): corrección, invalidación, sin cambio de contrato"
owner: Claude (QA)
status: pending
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
