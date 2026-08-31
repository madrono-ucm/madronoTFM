# Progreso del entregable "wow" — mapa animado del grafo de Madrid

**Qué es el resultado final:** un HTML autónomo, publicado en GitHub Pages,
con el grafo de ~1.798 nodos de tráfico sobre Madrid **latiendo hora a hora**
con la previsión de los dos STGNN (`trafico` + `calidad_aire`), las aristas
más influyentes iluminándose en la propagación, un índice de salud 0-100 por
nodo, capa "modelo vs persistencia", panel glass-box por arista y pulso de
distrito. Día curado con selector (viernes lluvioso / día de ozono / día de
partido / día tranquilo). Respaldo offline: tira de 6 fotogramas PNG para la
memoria.

**Coste:** cero AWS nuevo. Todo se hace en local sobre datos ya en Gold y los
ONNX vendorizados. El pipeline sigue congelado.

## Cómo se ve el progreso

- **`viz/mapa_trafico_madrid.html`** se **re-publica en cada milestone** a la
  misma URL de Pages → el enlace siempre muestra el estado más reciente, y el
  entregable final se ve **crecer** en vez de aparecer al final.
- **`viz/mapa_frames.png`** se regenera con cada re-publicación.
- `git log --oneline -- viz/` es la línea temporal del entregable.
- Esta tabla es la fuente de verdad del estado.

| URL publicada | _(pendiente de M4 — `FIL_35` la fija en Pages)_ · local: `python -m http.server -d viz/mapa` |
|---|---|
| Último milestone alcanzado | **M4 (código) — capas ricas E2/E4/E6** · hosting pendiente de acción del usuario (G8) |
| Fecha | 2026-08-31 (objetivo era 09-10 — 10 días de adelanto) |
| Siguiente | M5 (`FIL_36`) — grafo como eje de la memoria — objetivo **2026-09-13** · y `FIL_38` (MTD) si se quiere |
| Fork Vía A/B | **Vía A** hecha hasta M4. Vía B (MTD, `FIL_38`) opcional a partir de aquí. |

## Fork abierto — decisión del usuario antes de M2

La ventana Gold consultable son **~14 días de agosto 2026** (tráfico/aire),
**15** (meteo), **5** (ruido), con partition projection deslizante que
puede tirar esas particiones cuando el calendario pase de mediados de
septiembre. Sobre esos datos la animación es **fina**: 2-3 días
laborable-vs-finde, sin lluvia / ozono / evento garantizados, ruido sólo
como constante diaria por distrito.

- **Vía A — datos del proyecto** (por defecto en los tickets): rápido, 1.798
  nodos, honesto sobre sus límites. **Exportar los slices Gold YA**
  (`FIL_33`, primera tarea) antes de perderlos.
- **Vía B — MTD como sustrato** (`FIL_38` adelanta): 30 meses, estaciones,
  días de lluvia reales, backtest de verdad — pero 554 sensores, sin ruido,
  y hay que escribir el adaptador primero (~2 días).

Recomendación: **Vía A** para el spine seguro; **Vía B** sólo si el
calendario respira tras M3.

## Milestones

| M | Ticket | Estado | Objetivo | Qué se ve en el mapa al cerrarlo |
|---|---|---|---|---|
| **M0** | — | ✅ hecho | 2026-08-30 | (plan y tickets cerrados; `FIL_31` sirve el STGNN de tráfico que alimenta todo) |
| **M1** | `FIL_32` | ✅ hecho | 2026-08-31 | `viz/grafo_madrid.json`: 1.798 nodos con distrito, 8.758 aristas, top-15 importancia, lookups aire/ruido. `viz/build_grafo_madrid.py` + 6 tests. |
| **M2** | `FIL_33` | ✅ hecho | 2026-08-31 | G1 resuelto (`viz/data/gold_slices/`, ~4,6 MB). `viz/data/prevision_animada.parquet` (129.456 filas = 1.798 × 24 h × 3 días: 08-19 / 08-23 / 08-26). Inferencia 24×3 de los 2 STGNN, aire IDW a nodos, ruido diario por distrito, índice de salud. `viz/build_prevision_animada.py` + 7 tests. |
| **M3** | `FIL_34` | ✅ hecho | 2026-08-31 | `viz/mapa/index.html` (deck.gl CDN, distritos de fondo sin tiles) + `data.json` 2,9 MB + `weather.json` + `meta.json`. Bucle 24 h play/scrub, selector día/métrica/horizonte, ticker meteo (E5), 15 arcos de importancia animados por flujo (E1), color por índice de salud (E7), marcador de skill. `viz/mapa_frames.png` (6 fotogramas) para la memoria. `viz/build_mapa_animado.py` + 6 tests. `viz/requirements.txt` (G10). |
| **M4** | `FIL_35` | 🟡 código hecho | 2026-08-31 | **E2** toggle modelo-vs-persistencia (color divergente + marcador de skill por fotograma). **E4** panel glass-box: clic en nodo → sparklines 24 h (tráfico obs/h1, NO₂/O₃) + aristas de importancia que lo tocan. **E6** pulso de distrito: 21 distritos ordenados por salud, reordenan con el reloj. `tests/test_mapa_animado.py` a 7. **Falta** publicar en Pages → **acción del usuario** (G8). |
| **M5** | `FIL_36` | ⬜ | 2026-09-13 | (entregable estable) — figura de la memoria + `DATA_SOURCES.md` + promoción de "city-planner inputs" y "hosted endpoint" + limitaciones §7.4. |
| **M6** | `FIL_37` | ⏸ condicional | 2026-09-14 | Capa de ruta que "respira" (E3): healthy vs fastest recalculada cada hora, selector de perfil. Sólo si el gate de `FIL_37` se abre (~09-08). |
| opc. | `FIL_38` | ⬜ opcional | 2026-09-12 | Tabla de backtest `§7` a 30 meses (MTD + meteo histórica). O, si se elige la Vía B del fork, el **sustrato de la animación**. |

## Gaps / riesgos reales (auditados 2026-08-30)

| # | Gap | Impacto | Estado |
|---|---|---|---|
| G1 | **Partition projection deslizante** — las particiones de agosto pueden dejar de consultarse pasada la 2.ª mitad de septiembre | Sin datos = sin mapa | ✅ **resuelto** — `viz/export_gold_slices.py` congeló las 4 tablas a `viz/data/gold_slices/` (2026-08-31, ~4,6 MB). A partir de aquí todo offline. |
| G2 | **Ruido es diario, por `(station, period, date)`** — no hay ruido horario | La capa de ruido animada no es construible | ✅ **asumido** — ruido = constante por distrito (LAeq periodo "T" del slice), 17/21 distritos con dato, resto = media ciudad. No animado. |
| G3 | **Ventana ~16 días de agosto** sin variedad meteo/eventos | Animación fina | ✅ **asumido** — 3 días data-driven (08-19 normal / 08-23 domingo tranquilo / 08-26 miércoles cargado). El *swing intradía* sí es real (salud 76→88 en el día cargado). |
| G4 | **Aire: IDW desde 11 estaciones del STGNN a 1.798 nodos** | Superficie suave, no resolución de calle | ⬜ pendiente de declarar en `FIL_36` §7.4 |
| G5 | **`importancia_aristas` es estática** (top-15 precalc.) | E1 no puede ser "importancia por hora" | ⬜ `FIL_34`: E1 = conjunto fijo animado por el flujo en los extremos |
| G6 | **Volumen**: 129.456 filas (1.798 × 24 h × 3 días) | HTML no-snappy si va todo inline | ⬜ `FIL_34`: JSON externo con `fetch` + redondeo. Parquet actual 1,9 MB. |
| G7 | **CI no recorre `viz/`** | Tests de viz no corren en CI | ✅ **resuelto** — `tests/test_grafo_madrid.py` + `tests/test_prevision_animada.py` bajo `tests/` (sí en CI). |
| G8 | **GitHub Pages sin habilitar** + repo usa `doc/` no `docs/` | No hay hosting hasta acción del usuario | ⬜ `FIL_35` — **acción del usuario** pendiente |
| G9 | Grafo `coords-knn8`, no `PROXIMO_A` reales de Neo4j | Aristas de proximidad, no topología de calle | ⬜ declarar en §7.4 (aditivo) |
| G10 | Deps nuevas (`pydeck`, `pyarrow`, `matplotlib`) sin declarar | Build no reproducible | ⬜ `viz/requirements.txt` en `FIL_34` |

## Checklist detallado

### M1 — `FIL_32` grafo canónico
- [ ] `viz/build_grafo_madrid.py` (función pura, sin credenciales)
- [ ] `viz/assets/distritos_madrid.geojson` (Bronze `barrios_distritos` o descarga única)
- [ ] `viz/grafo_madrid.*` — 1.798 nodos (id/lat/lon de `node_coords`/distrito por PIP), aristas (a/b/length_m/weight), lookup estación_aire→nodo + distrito→nodos
- [ ] `tests/test_grafo_madrid.py` (**bajo `tests/`**, no `viz/` — CI)
- [ ] primer commit de `viz/mapa_trafico_madrid.html` (grafo estático)

### M2 — `FIL_33` prevision_animada
- [ ] **exportar slices Gold a `viz/data/gold_slices/` YA** (G1) — tráfico/aire/meteo/ruido
- [ ] días curados **data-driven** (2-3, laborable vs finde, margen ≥1,5 d)
- [ ] `viz/build_prevision_animada.py` — inferencia 24× sliding-window, 2 patrones de llamada (tráfico / aire), `festivos` de `modelado.features.build`
- [ ] aire → nodos por IDW; ruido → constante diaria por distrito (G2)
- [ ] índice de salud 0-100 documentado
- [ ] `viz/data/prevision_animada.parquet` + tests bajo `tests/` (formas / NaN / persistencia real)

### M3 — `FIL_34` mapa núcleo (E1/E5/E7)
- [ ] `viz/requirements.txt` (pydeck, pyarrow, matplotlib) (G10)
- [ ] `viz/build_mapa_animado.py` → HTML (pydeck, Carto Positron) + JSON de datos externo (G6)
- [ ] hero: Scatterplot + Line; E1 = top-15 aristas fijas animadas por flujo (G5)
- [ ] E5: bucle 24 h, controles, ticker meteo (Ayto., días curados), selector de día, toggle horizonte
- [ ] E7: selector de métrica (tráfico/NO₂/O₃/salud) + salud por defecto; ruido = capa de contexto
- [ ] `viz/mapa_frames.png` (tira de 6, distritos de fondo, sin tiles)

### M4 — `FIL_35` capas ricas + hosting
- [ ] E2 ghost modelo-vs-persistencia + marcador de skill
- [ ] E4 panel glass-box por arista (curvas 24 h + "explicado por")
- [ ] E6 pulso de distrito (21 distritos, reordenan con el reloj)
- [ ] layout final (controles / timeline / panel de contexto / ticker)
- [ ] habilitar GitHub Pages (Settings — **acción del usuario**, G8) + rama `gh-pages`
- [ ] enlace en `README.md` raíz y aquí

### M5 — `FIL_36` eje memoria
- [ ] figura + subsección "Visualización animada…" (coord. `VIKT_10`)
- [ ] `DATA_SOURCES.md` (CC BY 4.0: MTD, meteo Comunidad)
- [ ] promoción de ítems de encuadre (city-planner inputs, hosted endpoint)
- [ ] **limitaciones §7.4** explícitas (G2/G3/G4/G5/G9)
- [ ] reestructura ligera del índice hacia el eje del grafo

### M6 — `FIL_37` ruta_saludable *(condicional — gate en el ticket)*
- [ ] gate abierto: `FIL_31` mergeada + M3 hecho hacia el ~2026-09-08
- [ ] tool `ruta_saludable` + router + modelo + tests
- [ ] coste multi-objetivo + `networkx` shortest path + perfiles + mejor hora
- [ ] evaluación Pareto (§7) + caso ciclista
- [ ] capa E3 en el mapa
