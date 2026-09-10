# VIC_41 — QA de `grafo_centralidad` (FIL_81): PageRank/Louvain, artefacto, explorador (2026-09-10)

Revisión de código + verificación numérica contra el artefacto real
committeado (`modelado/evaluation/artifacts/grafo_centralidad.json`), sin
tocar AWS ni Neo4j (todo el análisis es offline sobre
`grafo/_data/grafo_urbano.json.gz`).

## 1. Propiedades numéricas — ✅ con una precisión a matizar

- `pagerank_suma = 0.999999` (redondeado a 6 decimales en
  `resumen_centralidad`) — dentro de la tolerancia 1e-6 que pide el
  ticket; el valor sin redondear de `nx.pagerank` está aún más cerca de 1.
- `comunidades.modularidad = 0.932` ∈ [0, 1) ✓. Nota honesta: es un valor
  **muy alto** para modularidad de red (0.3–0.7 es lo típico); no es un
  bug — `comunidades_vs_barrios` corre Louvain sobre `G_prox` (grafo de
  proximidad espacial, no el de transporte `CONECTADO_CON`), y los grafos
  de proximidad geográfica tienden a una estructura de comunidad muy
  marcada por construcción (las aristas son casi todas locales).
- `n_comunidades = 54` frente a `n_barrios = 131` — sano (>1, mucho menor
  que el nº de nodos del componente de proximidad).
- **Betweenness NO se reutiliza de la curva de robustez — se recalcula.**
  `centralidad_transporte()` (línea 104) llama
  `nx.betweenness_centrality(H, normalized=True, seed=42)` sobre el
  componente mayor completo. `curva_robustez()` (línea 326) llama la
  misma función con los mismos parámetros en su primera iteración
  (`i=0`, antes de quitar ningún nodo) sobre el mismo `H0`. `main()`
  invoca ambas funciones en la misma ejecución (`cent =
  centralidad_transporte(...)` y, más abajo, `res =
  resiliencia_transporte(...)` → `curva_robustez(...)`), así que el
  betweenness del grafo completo se calcula **dos veces** con entradas
  idénticas — el resultado es correcto (ambos cálculos coinciden), pero
  es trabajo duplicado y evitable. No es la duplicación que sugiere el
  ticket (recalcular en cada baja de `curva_robustez`, que es intencional
  y necesaria — el grafo cambia en cada paso), sino la del **paso 0**
  frente a `centralidad_transporte`. Abierto `FIL_85` (ver abajo).

## 2. Caveat de modelado presente — ✅

`resumen_centralidad()._nota` lleva el mismo aviso que
`grafo_resiliencia.json` sobre `CONECTADO_CON` = un viaje representativo
por línea, red poco mallada por construcción — confirmado por lectura
directa del JSON committeado.

## 3. Sin GDS, sin Neo4j en caliente — ✅

`grep -rn "gds\.\|gds\.session\|graph\.project"` sobre
`modelado/grafo_analitica/` y `viz/build_grafo_explorador.py`: 0
resultados. `centralidad_transporte`/`resumen_centralidad` operan sobre
un `networkx.Graph` ya materializado en memoria desde el snapshot local;
ninguna llamada a un driver de Neo4j en ese módulo.

## 4. Explorador — ✅ (con una corrección a las rutas que cita el propio ticket)

El ticket apunta a `viz/build_grafo_explorador.py` y
`tests/test_grafo_explorador.py`, pero esos ficheros son el **explorador
estático alternativo** (HTML embebido) y no mencionan `centralidad` en
absoluto. La pieza real es otra:

- `asistente/routers/grafo_explorador.py::_centralidad()` lee
  `grafo_centralidad.json` (con guarda `if not _CENTRALIDAD.exists()`) y
  lo expone dentro de `GET /grafo/explorador/analisis` junto a
  `cobertura_aire`, `sensores_por_distrito`, `stgnn_aristas_influyentes`
  y `resiliencia`.
- **Sí tiene cobertura de test real**:
  `asistente/tests/test_grafo_explorador_router.py::test_analisis_ensambla_cobertura_y_ficheros`
  (líneas 115-116) verifica `"top_pagerank" in a["centralidad"]` y
  `"modularidad" in a["centralidad"]["comunidades"]`.

## 5. Reproducibilidad — ✅ para `centralidad_transporte`; no verificable end-to-end en este entorno

Ejecuté `centralidad_transporte()` dos veces sobre el grafo real
(`grafo/_data/grafo_urbano.json.gz`, mismo `G_conn`/`nombres`): el CSV
resultante es **byte-idéntico** entre ambas corridas (comparación de
cadena exacta, no solo por columnas — `run1 == run2` → `True`). El JSON
`grafo_centralidad.json` no lleva ningún campo de timestamp, así que la
igualdad esperada es *exacta*, no "salvo campo `generado`".

No pude ejercer el pipeline completo (`main()`, que también llama
`comunidades_vs_barrios` → Louvain) dos veces de extremo a extremo en
esta EC2: el `.venv` compartido tiene `networkx==2.6.3`, que no trae
`nx.community.louvain_communities` (añadida en 2.8) — **el mismo
problema ya documentado y abierto en `FIL_61`** (severidad baja, CI con
entorno fresco pasa en verde). No es una regresión de `FIL_81`: los 2
tests que fallan en la suite (`test_comunidades_devuelve_ari_nmi`,
`test_resumen_centralidad`) fallan exactamente en la llamada a
`louvain_communities`, no en ningún código nuevo de centralidad —
confirmado leyendo el traceback y el propio código.

`.venv/bin/python -m pytest modelado/tests/test_grafo_analitica.py asistente/tests/test_grafo_explorador_router.py tests/test_grafo_explorador.py`:
**22 passed, 2 failed** (los 2 de `FIL_61`, preexistente). Los tests de
`test_grafo_explorador_router.py` y `test_grafo_explorador.py` (que no
dependen de Louvain) pasan en su totalidad.

## 6. Hallazgos para la memoria (para que los recoja `VIC_38`)

- Top-3 por PageRank: **Castellana - José Vasconcelos** (0.001378),
  **Santo Domingo** (0.001169), **Plaza Castilla** (0.000972) — las tres
  paradas EMT, coherente con ser nodos de alto grado en la red modelada.
- Top-3 por intermediación: **Canillejas** (0.314), **Metro O Donnell**
  (0.291), **Aeropuerto T1 - Salidas** (0.259) — perfil distinto al de
  PageRank: son puntos de paso obligado en la topología modelada
  (aeropuerto, nodos periféricos), no los de mayor grado.
- **54 comunidades Louvain** sobre el grafo de proximidad frente a **131
  barrios** reales — `ARI=0.362`, `NMI=0.754`: la estructura de comunidad
  del grafo captura razonablemente la geografía de barrios (NMI alto) sin
  ser una partición idéntica (ARI moderado), esperable porque Louvain no
  conoce los límites administrativos.
- Recordar el mismo caveat que `VIC_36`/`grafo_resiliencia.json`: estos
  números de centralidad son sobre el grafo **tal como se modela**
  (`CONECTADO_CON` = 1 viaje/línea), no un diagnóstico operativo real de
  EMT/Metro.

## Veredicto

Publicable en §6/§7 tal como está (cifras reales, deterministas, con
caveat correcto). Un solo hallazgo de ingeniería, menor y no bloqueante:
recomputación evitable de un betweenness idéntico — `FIL_85`.
