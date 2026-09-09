---
kind: fil
title: "Resiliencia estructural de la red de transporte real — puntos de articulación, puentes, ataque dirigido (§7 / FIL_36)"
owner: Filippos (interactive)
status: done
resolved_at: "2026-09-09"
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_51, FIL_52]
milestone: "M7"
target: "2026-09-14"
---

## Resultado (2026-09-09)

Implementado en `modelado/grafo_analitica/analisis.py` (5 funciones nuevas +
`_figura_resiliencia`), tests en `modelado/tests/test_grafo_analitica.py`
(grafo sintético de 2 líneas + triángulo), artefactos regenerados. Suite
verde (grafo 113 / grafo_analitica 10).

Hallazgos sobre `CONECTADO_CON` (componente mayor: 3.053 paradas / 3.641
aristas no dirigidas tras colapsar sentidos y líneas solapadas):

- **683 puntos de articulación** — paradas cuya caída parte la red.
- **740 puentes = 20 % de las aristas** — tramos sin ruta alternativa.
- **k-core máximo = 2** (2.319 paradas, todas EMT): la red modelada
  apenas tiene mallado por encima de grado 2.
- **Curva de robustez**: al eliminar el 5 % de las paradas, el ataque
  dirigido (por intermediación) deja el fragmento mayor en **39,6 %** de la
  red, frente a **89,1 %** con fallo aleatorio — separación grande y clara,
  buena figura para la defensa.

**Caveat documentado** (`_nota` en `grafo_resiliencia.json`):
`CONECTADO_CON` modela un único viaje representativo por línea (ver
`grafo/relaciones.py::conectado_con`), sin ramales ni servicios paralelos —
la red resultante es intrínsecamente poco mallada. Los hallazgos valen para
el grafo tal como se modela (razonamiento sobre estructura y sobre el propio
modelo), no como diagnóstico operativo de la EMT/Metro reales.

Artefactos: `modelado/evaluation/artifacts/grafo_resiliencia.{json,png}`
(gitignored; se versionan con `git add -f`, mismo criterio que los de
`FIL_52`).

--- encuadre original ---

## Motivación

`FIL_52` ya produce centralidad (grado/intermediación/cercanía) y comunidades
Louvain sobre el grafo urbano real. Lo que **no** contesta es la pregunta que
mejor justifica haber modelado el transporte como grafo navegable
(`CONECTADO_CON`): **¿qué le pasa a la red si caen sus nodos/aristas
críticos?** Es un análisis de *resiliencia* clásico de teoría de grafos
(cut vertices / cut edges / robustez frente a ataque dirigido) y hoy no hay
ninguno en el repositorio.

Da material directo para `§7` / `FIL_36` ("el grafo como eje de la memoria")
y para la defensa: una figura de "curva de robustez" es un resultado
visual fuerte que ningún enfoque tabular expresa de forma natural.

## Hallazgo que lo habilita (verificado en vivo esta sesión, 2026-09-09)

Inventario en vivo de la instancia AuraDB real (`5c111cec`):

- Grafo: **9.633 nodos / 72.310 relaciones**. `CONECTADO_CON` = **11.998**
  aristas (emt 11.418 · metro 480 · metro_ligero 100), 4.056
  `:ParadaTransporte` (3.072 emt/CRTM · 680 bicimad · 250 metro · 53
  metro_ligero · 1 emt/realtime). 681 paradas aisladas (680 son bicimad,
  sin línea por diseño). Grado medio 5,9 en `CONECTADO_CON`, máx 56.
- **APOC 2026.08.0 completo e in-DBMS** (`apoc.algo.dijkstra` verificado en
  vivo: Retiro→Sol devuelve un camino real ponderado por `distancia_m`,
  2.336 m / 11 saltos sobre `PROXIMO_A`).
- **"Aura Graph Analytics" (GDS) disponible pero *versionless* y por
  sesión**: `gds.graph.project` falla pidiendo `sessionId` o parámetros de
  creación de sesión (`memory`, `provider`, `region`, `ttl`) —
  `gds.session.getOrCreate(...)` existe. Es GDS serverless efímero, no
  in-DBMS. **No se usa en este ticket** (ver abajo).

## Alcance — `modelado/grafo_analitica/analisis.py` (`networkx`, offline)

Extiende el módulo de `FIL_52`, mismo patrón (cero AWS, cero Neo4j,
`networkx` sobre `grafo/_data/grafo_urbano.json.gz` de `FIL_51`). Añade:

1. **Puntos de articulación** (`nx.articulation_points`) de la componente
   mayor de `CONECTADO_CON`: paradas cuya eliminación parte la red en dos.
   Tabla con nombre legible + modo + nº de componentes tras eliminar + tamaño
   del mayor fragmento resultante. Top-15 por daño.
2. **Puentes** (`nx.bridges`): aristas (tramos entre dos paradas
   consecutivas de una línea) sin ruta alternativa. Agregado por
   `(modo, linea)` — qué líneas son "cadenas" sin redundancia.
3. **Descomposición k-core** (`nx.core_number`): el "núcleo" de la red
   (paradas en el k-core máximo) frente a la periferia colgante. Distribución
   de coreness + qué modos dominan el núcleo.
4. **Curva de robustez frente a ataque dirigido**: eliminar iterativamente
   la parada de mayor intermediación (recalculada cada N pasos) y registrar
   el tamaño relativo de la componente mayor. Comparar contra la baseline de
   fallo **aleatorio** (media de k repeticiones con semilla fija). Figura:
   dos curvas (dirigido vs aleatorio), eje X = fracción de nodos eliminados.

Salidas nuevas en `modelado/evaluation/artifacts/`:
- `grafo_resiliencia.json` — puntos de articulación (top), resumen de
  puentes por línea, resumen k-core, puntos de la curva de robustez.
- `grafo_resiliencia.png` — figura de 2–3 paneles (curva de robustez +
  barh de puntos de articulación por daño + histograma de coreness).

Reutiliza `construir_grafos`, `nombres_transporte` y el filtro de componente
mayor que ya existen en el módulo. Añade una subsección para la memoria
(coordinar con `VIKT_10`).

## Por qué NO usar GDS aquí

- `nx.articulation_points` / `nx.bridges` / `nx.core_number` son exactos en
  `networkx` y el grafo cabe en memoria de sobra (12k aristas). No hay
  ganancia de precisión ni de tiempo.
- `gds.session.getOrCreate` provisiona un recurso cloud efímero con un
  tamaño de memoria declarado — **acción con coste potencial** y con un
  mínimo facturable en tiers de pago (no se ha confirmado el tier exacto de
  esta cuenta). No merece la pena para un cálculo que `networkx` hace en
  segundos y de forma reproducible sin credenciales — mismo criterio que ya
  fijó `FIL_52`.
- Si en el futuro se quiere la versión nativa (p. ej. para la memoria
  "ejecutado en la propia BD de grafo"), queda como nota: `gds.session.*` +
  `gds.articulationPoints` / `gds.bridges` / `gds.kcore` existen en el
  catálogo de esta instancia.

## Criterios de aceptación

- `python -m modelado.grafo_analitica.analisis` sigue verde y produce los
  artefactos nuevos además de los de `FIL_52` (sin romper los existentes).
- Tests en `modelado/tests/test_grafo_analitica.py` cubren las funciones
  nuevas con un grafo pequeño sintético (patrón del test existente).
- La curva de robustez muestra la separación esperada (el ataque dirigido
  degrada la componente mayor mucho antes que el fallo aleatorio) — si no,
  documentar por qué (p. ej. red ya muy fragmentada de base).

## Restricciones

- Offline. Cero AWS, cero Neo4j, cero GDS. Solo `networkx` + `matplotlib`
  (ya disponibles).
- No tocar `asistente/` ni `viz/` ni infraestructura.
