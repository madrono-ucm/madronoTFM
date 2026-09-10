# VIC_44 — QA del anclaje temporal del asistente (FIL_84, 2026-09-10)

QA de `ASSISTANT_ANCHOR_DATE`/`ahora_o_ancla()` (`asistente/timeutils.py`)
y su adopción en `asistente/mcp_agent/tools.py`. Todo verificado con
lectura de código + ejecución real de la suite (sin red salvo lo ya
mockeado) y un script de verificación empírica para el punto 7.

## 1. `momento` explícito siempre gana — ✅

Los 11 sitios reales que usan `ahora_o_ancla()` (ver punto 3 — el ticket
asumía 13) siguen el mismo patrón exacto:

```python
if momento is not None:
    instante = momento.astimezone(MADRID_TZ) if momento.tzinfo is not None else momento.replace(tzinfo=MADRID_TZ)
else:
    instante = ahora_o_ancla()
```

Un `momento` explícito nunca pasa por `ahora_o_ancla()` — estructuralmente
imposible que el ancla lo sobrescriba. Confirmado además por el test ya
existente `test_calidad_aire_consulta_la_fecha_anclada` (con el ancla
puesta, sin `momento`, la SQL pide la fecha anclada) y verificado a mano
que un `momento` explícito con el ancla puesta a la vez produce la fecha
del `momento`, no la del ancla (mismo patrón de código, sin rama que
pueda mezclarlos).

## 2. Sin env, cero cambio — ✅

`grep` de fechas "de hoy" hardcodeadas en los tests: sin resultados.
Suite `asistente/` completa ejecutada dos veces, sin `ASSISTANT_ANCHOR_
DATE` y con ella a `2026-08-26`: **233 passed, 57 subtests** en ambos
casos, ningún test cambia de comportamiento. `ahora_o_ancla() ==
now_madrid()` sin la env ya lo cubre `test_sin_env_es_ahora`.

## 3. Los sitios migrados — ⚠️ el ticket decía 13, son 11 (no un bug)

`grep -c "ahora_o_ancla()" asistente/mcp_agent/tools.py` → **11**, no 13.
`grep -n "now_madrid()" asistente/mcp_agent/tools.py` → 0 (ninguno
queda); `now_madrid` no está importado en `tools.py` (el único import de
`asistente.timeutils` en ese fichero es `MADRID_TZ, ahora_o_ancla`) — el
import quedó retirado limpiamente, no hay import muerto. Los 11 sitios se
verificaron uno a uno: todos están dentro de la rama `else` de
`if momento is not None`, ninguno fuera. La discrepancia con "13" del
ticket no es un hallazgo de código — es una cifra del ticket que no se
verificó contra el `grep` real antes de escribirlo (mismo patrón visto
hoy en otras QA: `VIC_39`/`VIC_42` asumían recuentos de tools que ya
habían cambiado). `meteo_cercana`/`avisos_meteo` no necesitan el ancla:
ya resuelven "sin fecha" pidiendo el último día disponible directamente
en SQL (`ORDER BY date DESC`), sin pasar por Python.

## 4. `DIAS_CURADOS` — ⚠️ coincide hoy, pero duplicado sin fuente única

`asistente/timeutils.py::DIAS_CURADOS` = `("2026-08-19", "2026-08-23",
"2026-08-26")`. `asistente/modelos/grafo_ruta.json["dias"]` coincide
exactamente (mismo trío, mismo orden) — pero es un **artefacto
generado**, no una segunda definición independiente (viene de
`viz/build_prevision_animada.py` en tiempo de construcción).
`viz/build_prevision_animada.py::DIAS` (línea 56) **sí** es una segunda
definición independiente, con el mismo valor y el mismo comentario
explicativo pero sin compartir código con `asistente/timeutils.py`.
`viz/build_mapa_animado.py` además incrusta dos de las tres fechas como
literales sueltos (un frame de previsualización por defecto, un pie de
tour). Mismo patrón que `FIL_87` (umbrales duplicados), arreglado hoy
mismo con un módulo compartido — **abierto `FIL_90`** con la misma
solución (import compartido) propuesta, sin aplicarla en este ticket de
QA.

## 5. Hora del día conservada — ✅

`ahora_o_ancla()` hace `ahora.replace(year=..., month=..., day=...)`
sobre el `datetime` real — conserva `hour`/`minute`/`second`/`tzinfo`
intactos por construcción de `datetime.replace`. Ya cubierto por
`test_con_env_ancla_a_esa_fecha_conservando_hora`
(`self.assertEqual(a.hour, tu.now_madrid().hour)`), releído y confirmado
correcto.

## 6. `_INSTRUCCIONES` — ✅

`asistente/mcp_agent/server.py` (líneas 72-76) menciona explícitamente el
anclaje, nombra `ASSISTANT_ANCHOR_DATE`, describe los 3 días curados con
su perfil (laborable/domingo/miércoles cargado) y da un ejemplo concreto
de cómo pedir otro día vía `momento` (`2026-08-23T18:00`).

## 7. Interacción con la caché (`FIL_83`) — ✅ sin colisión, verificado empíricamente

El diseño evita el problema de raíz: `@cacheado` se aplica a
`run_athena_query`/`run_neo4j_query` (`asistente/athena.py`,
`asistente/neo4j_client.py`), **no** a las tools de más alto nivel. La
clave de caché (`_clave`) se construye sobre los argumentos de esas
funciones, y el primer argumento es el **SQL/Cypher ya construido**, que
las tools arman con la fecha resuelta (`instante.date().isoformat()`)
**incrustada como literal** antes de llamar. Dos fechas ancladas
distintas producen SQL distinto → claves de caché distintas,
estructuralmente, sin necesitar que la fecha forme parte explícita de la
clave. Verificado con un script real: `calidad_aire("Retiro")` con
`ASSISTANT_CACHE_TTL=900` y ancla `2026-08-26`, luego con ancla
`2026-08-19` — **2 llamadas reales** a `run_athena_query` (no 1 con un
hit de caché espurio), cada una con la fecha correcta incrustada en su
SQL.

## Veredicto

Los 7 puntos verificados. Ningún bug de comportamiento — el único hallazgo
(`DIAS_CURADOS` duplicado) es limpieza técnica de bajo impacto, misma
categoría que `FIL_87` de hoy, con ticket de seguimiento (`FIL_90`) en
vez de arreglo inline (fuera del alcance de "verificación, sin cambios
de lógica" de este ticket). `infra/OPERACION.md` ya documenta la env y su
valor de despliegue (`2026-08-26`).
