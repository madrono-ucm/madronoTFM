---
id: 34
slug: bronzewriter-hora-madrid
title: 'BronzeWriter y particionado: usar hora de Madrid en vez de UTC'
status: done
force: true
allow_infra_apply: false
branch: task/034-bronzewriter-hora-madrid
pr_number: 81
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/81
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T09:58:07.509082+00:00'
started_at: '2026-08-15T09:53:57.531209+00:00'
submitted_at: '2026-08-15T09:57:01.705355+00:00'
merged_at: '2026-08-15T09:57:04Z'
---

## Contexto

Todos los datos ya en producción real (Bronze) usan UTC (`+00:00`) tanto en
`ingested_at`/`measured_at` como en el particionado `fecha=.../hora=...` de
`BronzeWriter`. El usuario quiere hora de Madrid en su lugar — no solo un cambio de
formato, sino que las particiones y los timestamps reflejen la hora local de
Madrid (con su desfase real, CET/CEST según la época del año).

Esta es la primera de varias tareas (034-037: base compartida + 3 lotes de
productores; 038: reempaquetar y redesplegar): esta tarea establece el mecanismo
compartido que todas las demás reutilizarán.

## Objetivo

1. Añadir un helper reutilizable para obtener "ahora" en hora de Madrid.
2. Hacer que `BronzeWriter` particione (`fecha=YYYY-MM-DD/hora=HH`) según hora de
   Madrid, no UTC.

## Alcance concreto

1. Añade a `ingesta/capturas/bronze.py` (o un módulo nuevo pequeño si lo prefieres,
   p.ej. `ingesta/capturas/tz.py`, y documenta por qué) una función
   `now_madrid() -> datetime` usando `zoneinfo.ZoneInfo("Europe/Madrid")` (librería
   estándar, sin añadir dependencias) — un `datetime` *aware* con ese tzinfo.
   **Verifica en este entorno que `zoneinfo.ZoneInfo("Europe/Madrid")` no lanza
   `ZoneInfoNotFoundError`** (algunos entornos mínimos no traen la base de datos
   IANA de zonas horarias); si fallara, añade `tzdata` a
   `ingesta/requirements.txt` como fallback y documenta que hará falta reconstruir
   la Lambda Layer (tarea 032) para que esto llegue a producción — no lo hagas tú
   en esta tarea, solo documéntalo si aplica.
2. Cambia `BronzeWriter.write_batch` para que, si no se pasa `moment`
   explícitamente, use `now_madrid()` en vez de `datetime.now(timezone.utc)`. El
   particionado (`partition_dir`) debe reflejar la fecha/hora de Madrid del
   momento de la captura.
3. Añade/actualiza tests: confirma que `partition_dir` con un `moment` construido
   en hora de Madrid produce la fecha/hora esperada (incluye un caso que cruce
   medianoche en UTC pero no en hora de Madrid, o viceversa, para probar que
   realmente se usa la zona horaria correcta y no solo el offset actual).
4. Actualiza el docstring de `bronze.py` y la sección relevante de
   `ingesta/README.md`.

## Restricciones

- NO toques ningún productor individual (`trafico_madrid.py` y demás) en esta
  tarea — sus propios `ingested_at`/`measured_at` se corrigen en las tareas
  035-037, que reutilizarán `now_madrid()` de esta tarea.
- NO despliegues nada en AWS ni reconstruyas la Lambda Layer en esta tarea.
- No añadas `pytz` ni otra dependencia de terceros para esto — `zoneinfo` de la
  librería estándar es suficiente.

## Criterios de aceptación

- `now_madrid()` existe, devuelve un `datetime` *aware* en `Europe/Madrid`, y no
  lanza error en este entorno (o el fallback con `tzdata` está documentado si hizo
  falta).
- `BronzeWriter` particiona según hora de Madrid por defecto.
- Todos los tests del proyecto siguen pasando.
