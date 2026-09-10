# VIC_42 — QA de `meteo_cercana` + `avisos_meteo` (FIL_82, 2026-09-10)

Verificación de las tools MCP 18 y 19, `asistente/mcp_agent/tools.py`
(`meteo_cercana`, `avisos_meteo`), sus routers HTTP y su registro en el
resto del repo. Metodología: lectura del código real, `grep` de
consistencia y `pytest` — sin necesidad de credenciales AWS reales (los
tests existentes mockean Athena).

## 1. Resolución "cerca de" vía grafo — ✅ correcto, pero sin el *fallback* que el ticket asumía

`meteo_cercana` resuelve la estación meteo más cercana con
`estaciones_meteo_cerca_query` (Neo4j, `PROXIMO_A` sobre
`:EstacionMedida{meteo}` de `FIL_65`) y solo entonces consulta Gold. Si el
grafo no responde (excepción o lista vacía) devuelve `disponible=False`
con `motivo` — **no cae a haversine sobre Gold**. Comprobado que esto no
es una laguna nueva: es el mismo patrón que ya usa `trafico_cercano`
(`asistente/mcp_agent/tools.py:758`, sin ningún fallback haversine
tampoco); `_haversine_m` solo lo usa `eventos_cercanos`, que no tiene nodo
de grafo dedicado (`:Evento` no existe) y por eso resuelve distancia
directamente, no como *fallback* de una consulta de grafo que falló. La
premisa del ticket ("verificar que el fallback existe y no siempre se
dispara") no aplica — no hay tal fallback en ningún `_cercano`, y no
hace falta uno para ser consistente con el resto del asistente.

## 2. Agregación por magnitud — ✅ correcto

`ultima` se calcula por magnitud tomando la fila con `(date, hour)` máximo
(`tools.py:2706-2713`), no una media diaria. La respuesta
(`LecturaMeteo`) incluye `fecha`/`hora` del dato, y el router
(`meteo_cercana.py:33-36`) los muestra en la explicación.

## 3. Orden de niveles de aviso — ✅ correcto

`_NIVEL_AVISO_RANK = {"verde": 0, "amarillo": 1, "naranja": 2, "rojo": 3}`
y `peor = max(deldia, key=rank)` (`tools.py:2651,2771`) — orden correcto.
`asistente/tests/test_meteo_avisos.py::test_nivel_mas_alto_del_ultimo_dia`
y `test_rank_niveles` cubren esto con niveles mezclados; ambos verdes.

## 4. Fiabilidad por frescura — ⚠️ inconsistencia real entre las dos tools

`avisos_meteo` sigue el contrato que ya usa el resto del asistente
(`avisos_meteo.py:38`: `fiabilidad = MEDIA if fecha else BAJA` — sin
`fecha` explícita, el dato es "el último día disponible", y con el
pipeline congelado desde el 30/8 eso es estructuralmente antiguo).

`meteo_cercana` **no tiene ningún parámetro `fecha`/`momento`** y su
router (`meteo_cercana.py:38`) devuelve **siempre** `fiabilidad=MEDIA`
en cuanto hay alguna lectura, sin ninguna rama BAJA por frescura. Con el
pipeline congelado, el dato que sirve es tan viejo como el de
`avisos_meteo`, pero se presenta con más confianza sin motivo. Abierto
`tasks/FIL_88_meteo-cercana-sin-fiabilidad-por-frescura.md` (severidad
baja, no bloqueante).

## 5. Registro en el resto del repo — ✅ ya está completo

`server.py` dice "19 tools" (líneas 85, 110); `_ESPERADAS` en
`asistente/tests/test_mcp_transport.py:33` incluye ambas, con
`test_list_tools_expone_las_19` verde; `asistente/README.md` líneas
53-54 documentan `GET /meteo-cercana` y `GET /avisos-meteo`, y las
filas 285-286 de su tabla de herramientas describen ambas con su fuente
Gold y ticket de origen. Nada que corregir aquí (a diferencia de lo que
`VIC_37` encontró para el resto del README antes de esta ronda).

## 6. `contexto_urbano` — ✅ degrada sin excepción

`contexto_urbano.py:166` incluye `"meteo"` en la tupla de tipos de
estación de medida a 1 salto; cuando no hay ninguna estación meteo
cercana, esa lista queda simplemente vacía para ese tipo — no hay ningún
acceso directo a un índice o atributo que pudiera fallar si falta. No se
encontró ningún test dedicado a este caso límite exacto (estación meteo
ausente) pero el código no tiene ninguna vía de excepción visible.

## Tests

`pytest asistente/tests/test_meteo_avisos.py` → 7/7 verdes. No se tocó
código de producción en esta ronda (el hallazgo del punto 4 se deja para
`FIL_88`, no se arregla aquí — es un cambio de contrato pequeño pero
real, mejor con su propio ticket y tests que un QA lo cuele sin revisión).

## Veredicto

Publicable/estable tal cual, con una única inconsistencia real y de
severidad baja (punto 4) documentada en `FIL_88`. El resto de las 6
verificaciones de la ticket: sin hallazgos.
