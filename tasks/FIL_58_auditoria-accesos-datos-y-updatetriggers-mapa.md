---
kind: fil
title: "Mapa animado — auditar las dos clases de bug de FIL_55 (accesos a datos sin guarda + updateTriggers incompletos)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
depends_on: [FIL_55]
resolved_at: "2026-09-01"
---

## Resolución (2026-09-01)

Barrido completo del `_TEMPLATE` en `doc/FIL-58-...md` (tabla función →
clave → cómo está acotada; tabla capa → state leído → en updateTriggers).

- **Clase 1 (acceso a `DATA` sin guarda): sin hallazgos.** `FIL_55`
  (`_mediaCiudad`) era el único caso; las otras 13 rutas que indexan
  `DATA` por clave calculada están acotadas a las claves reales de
  `data.json` o interceptan las métricas virtuales antes.
- **Clase 2 (`updateTriggers` incompletos): 1 hallazgo menor, corregido.**
  La capa `sel` (aro de selección de nodo) tenía `getRadius:nodeRmin()*3`
  (depende de `state.view.zoom`) sin su `updateTrigger` → el aro no
  reescalaba al hacer zoom con el ratón. Añadido
  `updateTriggers:{getRadius:[state.view.zoom]}`. Impacto bajo.

`viz/mapa/index.html` regenerado; `tests/` + `viz` (`npm test`) en verde.

## Contexto

`FIL_55` destapó dos patrones frágiles en `_TEMPLATE`
(`viz/build_mapa_animado.py`) y los arregló **solo donde reventaba**.
Conviene barrer el fichero entero por si quedan más casos:

1. **Accesos a `DATA[dia][clave]` / `META[...]` sin guarda** cuando la
   clave puede ser una métrica virtual de `FIL_45` (`salud_perfil`,
   `dosis_no2`, `dosis_o3`) o simplemente no existir. `_mediaCiudad()`
   hacía `DATA[dia]["salud_perfil"][hora]` → `undefined[hora]`.
2. **Capas deck.gl cuyo `updateTriggers` no lista todos los `state.*`**
   que leen sus accessors → el mapa no se repinta al cambiar ese estado.
   `FIL_55` añadió `state.perfil` / `state.escala` al `trig` de los nodos
   y `getTargetColor` al `ArcLayer`.

## Objetivo

- Recorrer cada función del `_TEMPLATE` que indexe `DATA[state.day]` o
  `DATA[dia]` con una clave calculada; para cada una, o bien la clave está
  acotada al conjunto real de claves de `data.json`, o hay una rama
  explícita para las virtuales. Lista en `doc/FIL-58-...md`.
- Para cada capa de `layers()` / `routeLayers()`: enumerar los `state.*` y
  `selNode` que leen sus `get*` accessors y confirmar que **todos** están
  en `updateTriggers`. Corregir los que falten.
- Añadir a `tests/test_mapa_animado.py` (o al test funcional de `FIL_56`)
  asserts que cubran los casos nuevos: p. ej. cambiar `state.hz` con la
  métrica `trafico` activa repinta; cambiar de día repinta la ruta.
- Revisar también `spark()`, `pulse()`, `edgePane()`, `resumen()`,
  `skill()` por el mismo tipo de acceso.

## Criterios de aceptación

- Documento con la tabla "función → clave → cómo está acotada" y
  "capa → state leído → en updateTriggers?".
- Cero accesos sin guarda y cero `updateTriggers` incompletos al cerrar.
- Los casos nuevos cubiertos por test.

## Restricciones

- Solo `viz/build_mapa_animado.py` (+ regenerar `viz/mapa/index.html`).
- Si algún hallazgo es cosmético (repintado que "se arregla solo" en el
  siguiente frame), documentarlo pero no inflarlo a bug.
