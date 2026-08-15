# 034 — `BronzeWriter` y particionado: hora de Madrid en vez de UTC

## Qué se implementó

Primera de una serie de tareas (034-038) para migrar el particionado y los
timestamps de la ingesta de UTC a hora de Madrid. Esta tarea establece el
mecanismo compartido:

1. **`now_madrid()`** (nueva función en `ingesta/capturas/bronze.py`): devuelve
   `datetime.now(ZoneInfo("Europe/Madrid"))` — un `datetime` *aware* con el
   desfase real de Madrid según la época del año (CET/UTC+1 en invierno,
   CEST/UTC+2 en verano), no un offset fijo. Usa `zoneinfo` de la librería
   estándar, sin añadir dependencias de terceros.
2. **`BronzeWriter.write_batch`**: cuando no se pasa `moment` explícitamente,
   ahora usa `now_madrid()` en vez de `datetime.now(timezone.utc)`. Como
   `partition_dir`/`partition_key` solo formatean el `moment` recibido (no
   hacían conversión propia), este único cambio basta para que el
   particionado (`fecha=YYYY-MM-DD/hora=HH`) refleje la hora local de Madrid
   por defecto. Los productores que ya pasan un `moment` explícito (p. ej.
   `measured_at` convertido a UTC) no cambian de comportamiento — solo cambia
   el valor por defecto.

## Decisión: dónde poner `now_madrid()`

Se añadió a `ingesta/capturas/bronze.py` (no un módulo `tz.py` nuevo) porque
es la única consumidora directa por ahora (`write_batch`) y ya es el módulo
compartido por todos los productores para todo lo relativo a Bronze — crear
un módulo nuevo de una sola función habría sido una capa extra sin beneficio
inmediato. Las tareas 035-037, que reutilizarán `now_madrid()` en los propios
productores para sus `ingested_at`/`measured_at`, importarán
`from ingesta.capturas.bronze import now_madrid` sin problema (no genera
import circular: `bronze.py` no importa nada de los productores).

## Verificación de `zoneinfo.ZoneInfo("Europe/Madrid")` en este entorno

Se comprobó explícitamente, tal como pedía el enunciado, que no lanza
`ZoneInfoNotFoundError` en este entorno (Python 3.14, Amazon Linux):

```
$ python3 -c "from zoneinfo import ZoneInfo; from datetime import datetime as dt
print(dt(2026,8,15,12,tzinfo=ZoneInfo('Europe/Madrid')))   # 2026-08-15 12:00:00+02:00 (CEST)
print(dt(2026,1,15,12,tzinfo=ZoneInfo('Europe/Madrid')))   # 2026-01-15 12:00:00+01:00 (CET)"
```

Ambos offsets (+02:00 en verano, +01:00 en invierno) son correctos, así que
**no hizo falta** añadir `tzdata` a `ingesta/requirements.txt` como
fallback. Queda documentado en el docstring de `now_madrid()` qué hacer si un
entorno futuro (p. ej. una imagen base de Lambda distinta) careciera de la
base de datos IANA: añadir `tzdata` al `requirements.txt` y reconstruir la
Lambda Layer (tarea 032) — no se ha hecho aquí porque no ha hecho falta, y
esta tarea no despliega nada en AWS de todos modos.

## Cambio adicional, dentro del mismo fichero: el sufijo `Z` del nombre de fichero

`write_batch` también genera el nombre del fichero a partir de `moment`
(`f"{moment:%Y%m%dT%H%M%SZ}_{sufijo}.json"`, con un literal `Z` — el sufijo
ISO-8601 que denota UTC). Con el cambio de esta tarea, `moment` ya no es UTC
por defecto, así que mantener el `Z` habría sido engañoso (el nombre del
fichero afirmaría UTC mientras que la hora real codificada es de Madrid). Se
quitó ese sufijo literal (`%Y%m%dT%H%M%S`, sin `Z`). No hay ningún consumidor
en el repo (Silver/Gold, infra, tests) que dependa del formato exacto del
nombre de fichero más allá de que termine en `.json` — se confirmó con
`grep` antes de tocarlo.

## Tests añadidos (`ingesta/tests/test_bronze.py`)

- `NowMadridTests`: `now_madrid()` devuelve un `datetime` *aware* con
  `tzinfo` igual a `ZoneInfo("Europe/Madrid")`, y su instante real coincide
  (con margen de segundos) con `datetime.now(timezone.utc)`.
- `MadridTimezoneDefaultTests`, con `now_madrid` sustituida vía
  `unittest.mock.patch` para controlar el instante:
  - Cruce de medianoche en invierno: `2026-01-15 00:30` hora de Madrid (CET,
    UTC+1) equivale a `2026-01-14 23:30` UTC — confirma que la partición usa
    `fecha=2026-01-15/hora=00` (Madrid), no `fecha=2026-01-14/hora=23` (UTC).
  - Mismo cruce en verano: `2026-08-15 01:30` hora de Madrid (CEST, UTC+2)
    equivale a `2026-08-14 23:30` UTC — confirma que se usa el desfase real
    de la época del año (+2), no un offset fijo de +1 codificado a mano.
  - Un `moment` explícito sigue teniendo prioridad sobre `now_madrid()`
    (que ni siquiera se llega a invocar, verificado con `assert_not_called`).

Se ejecutó la suite completa del proyecto
(`python3 -m unittest discover -s ingesta/tests -t .` desde la raíz del
repo): **254 tests, todos en verde**, sin ninguna regresión en los tests
existentes de `BronzeWriter` (modo local y modo S3, que pasan un `moment`
explícito y por tanto no se ven afectados por el nuevo valor por defecto).

## Restricciones respetadas

- No se ha tocado ningún productor individual (`trafico_madrid.py` y demás)
  — eso es el alcance de las tareas 035-037, que reutilizarán `now_madrid()`.
- No se ha desplegado nada en AWS ni reconstruido la Lambda Layer.
- No se ha añadido `pytz` ni ninguna otra dependencia de terceros — solo
  `zoneinfo` de la librería estándar, y no hizo falta `tzdata`.

## Relevante para tareas futuras

- `now_madrid()` está lista para que las tareas 035-037 la importen desde
  `ingesta.capturas.bronze` y la usen en sus propios `ingested_at`/
  `measured_at` (hoy en UTC en los 14 productores).
- El nombre de fichero que genera `write_batch` ya no lleva el sufijo `Z`
  (ver sección de arriba) — si alguna tarea futura documenta o parsea ese
  nombre en algún sitio, debe tener en cuenta que ya no es literal UTC.
- La tarea 038 (reempaquetar y redesplegar) es la que hará que este cambio
  llegue a producción real: hasta entonces, el `.zip` de `ingesta/` ya
  desplegado en las 14 funciones Lambda (tareas 031/033) sigue particionando
  en UTC.
