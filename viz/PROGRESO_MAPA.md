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

| URL publicada | _(pendiente de M3 — `FIL_35` la fija en Pages)_ |
|---|---|
| Último milestone alcanzado | **M0 — plan cerrado** |
| Fecha | 2026-08-30 |
| Siguiente | M1 (`FIL_32`) — grafo canónico exportado |

## Milestones

| M | Ticket | Estado | Fecha | Qué se ve en el mapa al cerrarlo |
|---|---|---|---|---|
| **M0** | — | ✅ hecho | 2026-08-30 | (plan y tickets cerrados; `FIL_31` sirve el STGNN de tráfico que alimenta todo) |
| **M1** | `FIL_32` | ⬜ | — | El grafo estático (nodos + aristas) sobre el basemap de Madrid. Sin animación. Primer commit de `mapa_trafico_madrid.html`. |
| **M2** | `FIL_33` | ⬜ | — | (sin cambio visible — genera `prevision_animada.parquet`: inferencia de los 2 STGNN sobre los días curados + baseline de ruido + índice de salud) |
| **M3** | `FIL_34` | ⬜ | — | **Primer HTML animado**: bucle de 24 h, play/scrub, color de nodo por métrica (índice de salud por defecto), aristas de importancia encendiéndose (E1), ticker meteo (E5), selector de día. |
| **M4** | `FIL_35` | ⬜ | — | Mapa "wow" completo: toggle modelo-vs-persistencia (E2), panel glass-box por arista (E4), pulso de distrito (E6). **Publicado en una URL de GitHub Pages.** |
| **M5** | `FIL_36` | ⬜ | — | (entregable estable) — figura de la memoria + `DATA_SOURCES.md` + promoción de "city-planner inputs" y "hosted endpoint" a entregado. |
| **M6** | `FIL_37` | ⏸ condicional | — | Capa de ruta que "respira" (E3): healthy vs fastest recalculada cada hora, selector de perfil (ciclista / aire / ruido / general). Sólo si el gate de `FIL_37` se abre. |
| opc. | `FIL_38` | ⬜ opcional | — | (sin cambio visible — tabla de backtest `§7` a 30 meses con MTD + meteo histórica) |

## Checklist detallado

### M1 — `FIL_32` grafo canónico
- [ ] `viz/build_grafo_madrid.py` (función pura, sin credenciales)
- [ ] `viz/grafo_madrid.*` — nodos (id/lat/lon/distrito/attrs), aristas (a/b/length_m/weight), lookup sensor→nodo
- [ ] `viz/tests/test_grafo_madrid.py`
- [ ] primer commit de `viz/mapa_trafico_madrid.html` (grafo estático)

### M2 — `FIL_33` prevision_animada
- [ ] días curados elegidos y justificados (sobre Gold ya presente)
- [ ] `viz/build_prevision_animada.py` — inferencia ONNX + baseline ruido + IDW + índice de salud
- [ ] `viz/data/prevision_animada.parquet`
- [ ] tests de formas / NaN / persistencia

### M3 — `FIL_34` mapa núcleo (E1/E5/E7)
- [ ] `viz/build_mapa_animado.py` → HTML autónomo (pydeck, Carto Positron)
- [ ] hero: Scatterplot + Line + Arc; E1 propagación
- [ ] E5: bucle 24 h, controles, ticker meteo, selector de día, toggle horizonte
- [ ] E7: selector de métrica + índice de salud por defecto
- [ ] `viz/mapa_frames.png` (tira de 6)

### M4 — `FIL_35` capas ricas + hosting
- [ ] E2 ghost modelo-vs-persistencia + marcador de skill
- [ ] E4 panel glass-box por arista (curvas 24 h + "explicado por")
- [ ] E6 pulso de distrito (21 distritos, reordenan con el reloj)
- [ ] layout final (controles / timeline / panel de contexto / ticker)
- [ ] GitHub Pages + enlace en `README.md` raíz y aquí

### M5 — `FIL_36` eje memoria
- [ ] figura + subsección "Visualización animada…" (coord. `VIKT_10`)
- [ ] `DATA_SOURCES.md` (CC BY 4.0: MTD, meteo Comunidad)
- [ ] promoción de ítems de encuadre (city-planner inputs, hosted endpoint)
- [ ] reestructura ligera del índice hacia el eje del grafo

### M6 — `FIL_37` ruta_saludable *(condicional — gate en el ticket)*
- [ ] gate abierto: `FIL_31` mergeada + M3 hecho hacia el ~día 8
- [ ] tool `ruta_saludable` + router + modelo + tests
- [ ] coste multi-objetivo + `networkx` shortest path + perfiles + mejor hora
- [ ] evaluación Pareto (§7) + caso ciclista
- [ ] capa E3 en el mapa
