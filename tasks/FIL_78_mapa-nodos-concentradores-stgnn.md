---
kind: fil
title: "Mapa: explicar los nodos concentradores del STGNN (panel arista/nodo + resalte de aristas)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_49, FIL_77]
milestone: "M7"
---

## Motivación (reporte del usuario)

Al clicar el nodo #5768 en el panel "arista/nodo" aparecían 8 conexiones,
mientras que cualquier otro nodo mostraba 1 o ninguna → parecía un error.

**No es un error.** `importancia_aristas` de la metadata del STGNN es un
**top-15 GLOBAL** de aristas por peso de importancia, no una adyacencia por
nodo. #5768 es un extremo de 8 de esas 15 aristas y #4848 de 6; el resto de
nodos, de 1. Son los **concentradores de flujo** del modelo (probables
grandes cruces). El panel lo presentaba como una lista plana sin contexto,
así que el nodo con 8 parecía anómalo, y la dirección (`a` influye en `b`)
se perdía al colapsarla a no dirigida.

## Hecho

- **`edgePane()`** reescrito:
  - `impDeg()` (memoizado) cuenta cuántas de las 15 aristas tocan cada nodo.
  - Si el nodo seleccionado toca ≥3 (`HUB_MIN`): cabecera destacada
    *"Nodo concentrador — N de las 15 aristas más influyentes del STGNN
    pasan por aquí."*; si no, la etiqueta neutra de siempre.
  - Cada arista como fila con **dirección** (`→ influye` / `← influido por`),
    id del otro nodo, **barra de peso** y el peso numérico, ordenadas por
    peso descendente.
- **Resalte en el mapa**: con un nodo seleccionado, las aristas de
  importancia que lo tocan van a plena intensidad y grosor; el resto se
  atenúan al 16 % de alfa y 45 % de grosor (`arcOn` / `arcTint` en la
  `ArcLayer`, con `selNode` en los `updateTriggers`).
- **Texto de la sección "Capa de color"**: nombra #5768 y #4848 como los
  concentradores de flujo del modelo y aclara que el arco-set es un top-15
  global.

## Verificación

- `tests/test_mapa_animado.py` (+`test_edgepane_explica_los_concentradores`,
  18) + `viz/test/mapa.test.mjs` jsdom (3) verdes; suite `tests/`+`viz/` (48).
- Playwright: clic en #5768 → cabecera "Nodo concentrador — 8 de las 15…"
  + 8 filas dirigidas ordenadas por peso (1.00 … 0.24); clic en #6767
  (no-hub) → etiqueta neutra + 1 fila `← #5768 · influido por · 0.91`.
- Republicado en `gh-pages`.

## Nota

Es un hallazgo del **STGNN `coords-knn8`** (el grafo del mapa animado), no
del grafo de Neo4j (capítulo 6 del recorrido guiado). Grafos distintos.
