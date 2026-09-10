---
kind: fil
title: "meteo_cercana no degrada fiabilidad por frescura (a diferencia de avisos_meteo/trafico_cercano)"
owner: Sistema
status: pending
depends_on: [FIL_82]
created_at: "2026-09-10"
---

## Contexto

`VIC_42` (QA de `meteo_cercana`/`avisos_meteo`, `FIL_82`) verificó el
contrato de frescura que el resto del asistente ya sigue (p.ej.
`avisos_meteo`, `asistente/routers/avisos_meteo.py:38`: `fiabilidad=MEDIA
if fecha else BAJA` — sin `fecha` explícita, el dato es "el último día
disponible", y con el pipeline congelado desde el 30/8 eso es
estructuralmente antiguo, así que se marca BAJA).

`meteo_cercana` (`asistente/mcp_agent/tools.py::meteo_cercana`) **no acepta
ningún parámetro `fecha`/`momento`** — siempre devuelve la última lectura
por magnitud (`ORDER BY date DESC, hour DESC`) sin forma de que el llamador
la ancle a una fecha concreta. Su router
(`asistente/routers/meteo_cercana.py:38`) devuelve **siempre**
`fiabilidad=MEDIA` en cuanto `disponible=True`, sin ninguna rama BAJA por
frescura — la única rama BAJA es "sin ninguna lectura en absoluto". Con el
pipeline congelado, esto sobre-reclama confianza: el dato es
estructuralmente tan antiguo como el de `avisos_meteo`, pero el asistente
lo presenta con una fiabilidad mayor sin motivo real.

## Alcance

- Añadir un parámetro `fecha: str | None` (o reutilizar `momento` como
  hacen `trafico_cercano`/`calidad_aire`) a `meteo_cercana`, filtrando el
  `WHERE` de Athena a esa fecha si se da.
- En el router, replicar el patrón de `avisos_meteo`:
  `fiabilidad = MEDIA if fecha else BAJA` cuando `disponible=True`.
- Test que cubra ambas ramas (con `fecha` explícita → MEDIA; sin `fecha` →
  BAJA), análogo a los que ya existen para `avisos_meteo` en
  `asistente/tests/test_meteo_avisos.py`.
- Actualizar el docstring de la tool y la fila de `asistente/README.md`
  (línea 285) para mencionar el nuevo parámetro.

## Criterios de aceptación

- `meteo_cercana` sin `fecha` → `fiabilidad=BAJA` en el router; con
  `fecha` → `MEDIA` si hay datos para ese día.
- Sin cambio de contrato para los llamadores existentes que no pasan
  `fecha` (sigue devolviendo la última lectura disponible, solo cambia la
  `fiabilidad` reportada).
- Tests nuevos en verde + suite completa de `asistente/` en verde.

## Notas

Severidad baja — no es un error de datos, solo una sobre-confianza en la
`fiabilidad` reportada mientras el pipeline está congelado. No bloquea la
entrega; se dejó fuera del propio `FIL_82` sin ticket de seguimiento hasta
ahora.
