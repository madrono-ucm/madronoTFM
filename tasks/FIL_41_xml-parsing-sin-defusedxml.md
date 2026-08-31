---
kind: fil
title: "Parseo XML de 4 feeds de ingesta con xml.etree.ElementTree en vez de defusedxml"
status: pending
created_at: "2026-08-30"
source: "VIC_26 (ronda 4 de evaluación técnica, bandit)"
severity: baja
---

## Qué está roto (verificado en vivo)

`bandit -r` (instalado por primera vez en esta sesión, nunca antes corrido
sobre este repo) marca `B405`/`B314` en 4 módulos de ingesta que parsean XML
de feeds externos de datos.madrid.es con `xml.etree.ElementTree.fromstring`
en vez de `defusedxml`:

- `ingesta/capturas/emt_incidencias_madrid.py:50` (import) y `:168`/`:238` (`ET.fromstring`)
- `ingesta/capturas/parques_jardines_madrid.py:49` y `:173`
- `ingesta/capturas/poi_madrid.py:135` y `:316`
- `ingesta/capturas/trafico_madrid.py:27` y `:177`

Verificado a mano que las 4 llamadas a `ET.fromstring` reciben el cuerpo
crudo de la respuesta HTTP de un feed externo (`requests.get(...).text`),
no un literal local ni un fixture de test.

## Por qué importa

`xml.etree.ElementTree` de CPython, desde 3.7.1, **no** resuelve entidades
externas por defecto (no es vulnerable a XXE clásico "leer un fichero
local"), pero **sí** sigue siendo vulnerable a expansión de entidades
internas ("billion laughs" / DoS por agotamiento de memoria) porque no
tiene los límites de profundidad/repetición que sí trae `defusedxml`. La
fuente es un endpoint oficial de datos.madrid.es -- no es entrada de un
usuario final -- pero sigue siendo una respuesta de red no firmada
criptográficamente: un feed comprometido, cacheado/modificado en tránsito,
o un cambio de endpoint sin que nadie lo note, alimentaría XML sin
sanitizar directamente al parser. Riesgo real bajo (fuente confiable, sin
antecedentes de abuso), pero el fix es tan barato que merece hacerse como
higiene defensiva, algo que ninguna auditoría manual anterior (`VIC_19`,
basada en `grep`) podía encontrar porque hace falta un analizador que
entienda específicamente patrones de parseo XML.

Cruzado contra `VIC_19`/`FIL_28` (la auditoría de seguridad manual previa,
centrada en credenciales): no hay solape, `VIC_19` no tocó parseo de XML.

## Qué hacer (propuesto, no aplicado aquí)

Sustituir, en los 4 ficheros:

```python
import xml.etree.ElementTree as ET
...
root = ET.fromstring(texto)
```

por:

```python
from defusedxml import ElementTree as ET
...
root = ET.fromstring(texto)
```

`defusedxml.ElementTree` es API-compatible con `xml.etree.ElementTree` para
el uso que hacen estos 4 módulos (`.fromstring`, `.findall`, `.findtext`,
`.text`, `.get`) -- cambio mecánico de una línea de import por fichero, sin
tocar el resto de la lógica de parseo. Añadir `defusedxml` a
`ingesta/requirements.txt`.

## Restricciones

- No se ha aplicado el cambio aquí (ticket de solo lectura, `bandit`
  instalado solo en el `.venv` local para esta auditoría).
- No degradar por seguirse esperando: los 4 tests de ingesta relevantes
  (`test_emt_incidencias_madrid.py`, `test_parques_jardines_madrid.py`,
  `test_poi_madrid.py`, `test_trafico_madrid.py`) deben seguir pasando
  igual tras el cambio -- son fixtures XML bien formados, no deberían verse
  afectados por los límites adicionales de `defusedxml`.

## Criterios de aceptación

- Los 4 imports cambiados a `defusedxml.ElementTree`.
- `defusedxml` añadido a `ingesta/requirements.txt`.
- Suite de tests de `ingesta/` sigue en verde tras el cambio.
- `bandit -r ingesta/capturas/` ya no reporta `B405`/`B314` para estos 4
  ficheros.
