---
kind: vic-eval
title: "Evaluación técnica — grafo/"
owner: Claude (QA)
status: done
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s grafo/tests -t .` — suite completa.
- Estado real de Neo4j (conteos de nodos/relaciones vía Cypher real) vs lo
  documentado en `doc/080`/`doc/094`/`doc/107` (aforos, parques, OSM).
- Confirmar si los gaps ya conocidos (enriquecimiento OSM limitado a
  muestra, `ML_01` sin usar el grafo para meteo) siguen igual.

## Criterios de aceptación

- Resultado real de la suite.
- Conteos reales de Neo4j, comparados con la última foto documentada.
- Cualquier discrepancia documentada, con ticket `FIL_*` si implica un
  cambio de código.

## Hecho (29/8)

- `python3 -m unittest discover -s grafo/tests -t .` → **100 passed** (1
  skipped, esperado).
- Estado real de Neo4j (Cypher directo): 9633 nodos (21 Distrito, 131
  Barrio, 4839 EstacionMedida, 4056 ParadaTransporte, 586 Lugar), 72310
  relaciones (131 PERTENECE_A, 9323 UBICADO_EN, 50858 PROXIMO_A, 11998
  CONECTADO_CON). Aforos (83 estaciones) y parques (203 lugares) siguen
  presentes, tal como documentó `FIL_04`/`FIL_08`/`doc/094`.
- **Enriquecimiento OSM sigue en 0** (`osm_categoria` no existe en ningún
  `:Lugar`) — gap ya conocido, sin cambios, no es un hallazgo nuevo.
- Nota menor (no es un bug): los conteos de `PROXIMO_A` con aforos/parques
  (45 y 171 respectivamente) no coinciden exactamente con los últimos
  números documentados (38 y 199) — el total de `PROXIMO_A` también creció
  (41031→50858), indicando que el grafo se ha recargado de nuevo desde
  entonces con algún cambio (posiblemente el propio `FIL_08` u otra
  recarga). No se investiga más a fondo: es evolución esperada de un grafo
  que se recarga periódicamente, no una regresión.
- Sin hallazgos que requieran un ticket `FIL_*`.
