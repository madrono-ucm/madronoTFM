---
kind: fil
title: "Reconstruir el grafo urbano real de Neo4j como artefacto offline (grafo_urbano.json)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: []
milestone: "M7"
target: "2026-09-08"
---

## Resolución (2026-08-31)

`grafo/exportar_grafo.py` — `construir()` replica el flujo de
`cargar_grafo.cargar_grafo()` (`extract` Athena/S3 → `nodos` → `relaciones`)
y serializa. `cargar()` lee el `.gz` sin AWS ni Neo4j. Reconstruido en vivo
contra la cuenta real:

| label | n |  | relación | n |
|---|---|---|---|---|
| Distrito | 21 | | PERTENECE_A | 131 |
| Barrio | 131 | | UBICADO_EN | 9.323 |
| EstacionMedida | 4.839 | | PROXIMO_A | **50.850** |
| ParadaTransporte | 4.056 | | CONECTADO_CON | **11.998** |
| Lugar | 586 | | | |

Sin avisos (todas las fuentes cargaron). `distancia_m` redondeada a entero,
ubicaciones a 6 decimales → `grafo/_data/grafo_urbano.json.gz` **~0,66 MB**
versionado (el `.json` de ~9 MB está en `.gitignore`).
`grafo/tests/test_exportar_grafo.py` (5). Substrato de `FIL_52`/`FIL_53`.

## Motivación

El grafo de Neo4j (5 labels, 4 relaciones, ~9.430 nodos) está infrautilizado:
las tools del MCP hacen `MATCH` de **1 salto**, y `ruta_saludable` / el mapa
ni lo tocan — enrutan sobre un export estático `coords-knn8` (la limitación
G9). `CONECTADO_CON` (la red de transporte real) y cualquier algoritmo de
grafo están **sin usar**. Sin acceso de escritura a la instancia Aura en
esta sesión, el desbloqueo es **reconstruir el mismo grafo offline** desde
las fuentes que ya usa `grafo/cargar_grafo.py`.

## Alcance

`grafo/exportar_grafo.py` — replica el flujo de `cargar_grafo.cargar_grafo()`
(`extract` Athena/S3 → `nodos` → `relaciones`) pero en vez de
`Neo4jLoader.load_*` **serializa a JSON**:

- `grafo/_data/grafo_urbano.json` (o release):
  - `nodos`: por label (`Distrito`, `Barrio`, `Lugar`, `EstacionMedida`,
    `ParadaTransporte`) con sus propiedades (incl. `ubicacion` lat/lon,
    `osm_*` de `enrich_lugares_con_osm`, `distancia_m` no aplica aquí).
  - `relaciones`: `PERTENECE_A`, `UBICADO_EN`, `PROXIMO_A` (con
    `distancia_m`), `CONECTADO_CON`.
  - `_meta`: fuente (Athena/S3), fecha, conteos por label/tipo.
- Degradación: si una tabla Gold ya no es consultable (projection
  deslizante), se salta esa fuente y se registra en `_meta.avisos` — el
  grafo se reconstruye con lo que haya.
- Función pura salvo `extract` (AWS). Tests bajo `grafo/tests/` con las
  fixtures existentes (no tocan AWS).

## Coste

Lecturas Athena/S3 (station lists, Bronce). Cero infra, cero escritura.
Cero Neo4j.

## Entregable

`grafo/_data/grafo_urbano.json` versionado (o, si pesa, en release + doc).
Substrato de `FIL_52` (analítica de grafo) y `FIL_53` (tool multi-salto).
