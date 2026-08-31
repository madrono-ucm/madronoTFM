# `viz/` — mapa animado del grafo de Madrid

El elemento "wow" del TFM: el grafo de **1.798 nodos de tráfico** sobre
Madrid, latiendo hora a hora con la previsión de los dos STGNN de grafo
(`trafico` + `calidad_aire`), con las 15 conexiones más influyentes del
modelo destacadas y un **índice de salud 0-100** por nodo.

Todo se genera **offline**, sin credenciales, a partir de los ONNX
vendorizados y de un snapshot congelado de la capa Gold.

## Reconstruir de cero

```bash
pip install -r viz/requirements.txt
python -m viz.export_gold_slices     # (solo si hay AWS_PROFILE; ya hay un snapshot commiteado)
python -m viz.build_grafo_madrid     # -> viz/grafo_madrid.json
python -m viz.build_prevision_animada # -> viz/data/prevision_animada.parquet  (~1 min)
python -m viz.build_mapa_animado     # -> viz/mapa/{index.html,data.json,...} + viz/mapa_frames.png
```

## Ver el mapa

**En vivo:** https://madrono-ucm.github.io/madronoTFM/ (rama `gh-pages`, `FIL_42`).

En local:

```bash
python -m http.server -d viz/mapa      # http://localhost:8000
```

Necesita red al abrir (bundle de deck.gl por CDN). La tira
`viz/mapa_frames.png` es el respaldo sin red y la figura de la memoria.

### Controles (panel izquierdo, en 5 grupos colapsables)

- **⏱ Tiempo**: los 3 días curados de agosto 2026 (miércoles normal /
  domingo tranquilo / miércoles cargado), play/slider (bucle de 24 h),
  horizonte *ahora / +1h / +3h / +6h* (afecta solo a la métrica *tráfico*).
- **🎨 Capa de color**: métrica (salud por defecto · tráfico · NO₂ · O₃ ·
  *salud (perfil)* · *dosis NO₂* · *dosis O₃*) con la leyenda pegada;
  **escala lineal / bandas OMS·UE** (en *bandas* el nodo se colorea por el
  umbral en que cae — NO₂ 25/40/100/200, O₃ 100/120/180/240 µg/m³ — y la
  leyenda **nombra** la banda, con paleta apta para deuteranopía);
  *modelo vs persistencia (E2)* (colorea por la divergencia STGNN(h1) −
  persistencia; el marcador de *skill* compara ambos contra el valor real).
- **♿ Salud · perfil de sensibilidad** (`FIL_45`): 9 perfiles con los
  mismos pesos que `ruta_saludable` (`FIL_37`) — general, ciclista,
  sensible_aire, sensible_ruido, asma_epoc, mayor, infancia,
  movilidad_reducida, trabajo_exterior; al elegir uno la métrica pasa a
  *salud (perfil)* (ponderación tráfico/NO₂/O₃/ruido propia del perfil).
  **"Mejor hora hoy"** (y la peor) por barrido de 24 h. **Confianza IDW**:
  capa opcional que marca los nodos lejos de las 11 estaciones de aire
  (gap G4). Las métricas *dosis NO₂ / dosis O₃* son la media de la
  exposición prevista de las próximas 8 h como % de la guía OMS.
  Guardarraíles siempre a la vista: agregados por zona, sin datos
  personales, describe el aire y la hora (no señala barrios), apoyo a la
  decisión — no consejo médico.
- **🧭 Vista**: cámara **2D / 3D**, **"encajar a Madrid"**, **"vista
  limpia"** (oculta todo el chrome para una captura); representación de los
  nodos **auto / puntos / barras (3D)** — en *barras* la columna sube donde
  las condiciones son **peores** (skyline de problema); y capas conmutables
  — nombres de distrito, hitos, ejes estructurantes (M-30, Castellana…
  *contexto*), parques grandes, textura del grafo (las 8.758 aristas).
- **Panel inferior (resumen)**: media de la ciudad de la métrica actual a
  lo largo de las 24 h (con la hora marcada), barras por distrito ahora, y
  meteo + skill del modelo.
- **🚶 Ruta saludable (E3)**: dos desplegables (origen·destino × perfil,
  los 9 de arriba); traza la ruta sana (verde) vs rápida (gris)
  recalculada cada hora.
- **Tooltip** al pasar el ratón por un nodo (id, distrito, salud/NO₂/O₃).
- **Panel derecho**: pestaña *distritos* (pulso: 21 distritos ordenados por
  salud, se reordenan con el reloj) / pestaña *arista-nodo* (clic en un
  nodo → curvas de 24 h + aristas de importancia que lo tocan).

## Limitaciones (memoria §7.4)

| # | Limitación |
|---|---|
| G2 | El **ruido** de la Red de vigilancia es **diario** (por estación/periodo/fecha), no horario → entra como constante por distrito, no como capa animada. |
| G3 | La ventana Gold consultable son ~16 días de agosto 2026 sin variedad meteorológica ni eventos. El contraste es laborable/finde y el *swing intradía*; no hay "día de lluvia". |
| G4 | La **calidad del aire** se interpola (IDW) desde las **11 estaciones** del STGNN a los 1.798 nodos → superficie suave, no resolución de calle. |
| G5 | La **importancia de aristas** es estática (top-15, precalculada al exportar el modelo). Los arcos son un conjunto fijo; lo que se anima es el tráfico en sus extremos. |
| G9 | El grafo es `coords-knn8` (proximidad entre sensores), no la topología de calle real de Neo4j (`PROXIMO_A`). Reentrenar con `--aristas-json` es trabajo aditivo. |

Honestidad de modelo: los STGNN de grafo **pierden a LightGBM en métricas
puntuales** (`trafico_prevista` / `calidad_aire_prevista`); se sirven y se
visualizan por la **explicabilidad de grafo**, no por precisión.

## Ítems de encuadre — estado

| Ítem | Estado |
|---|---|
| **city-planner inputs** | ✅ **entregado** — la vista agregada de importancia de aristas + el pulso de distrito son artefactos de planificación. |
| **hosted endpoint** | ✅ **entregado** — publicado en **https://madrono-ucm.github.io/madronoTFM/** (rama `gh-pages`, `FIL_42`). No es una API de producción. |
| **open dataset** | encuadre — se **consume** MTD (`FIL_38`), no se publica un dataset propio. |
| **cyclist / movilidad reducida routing** | ✅ **entregado** — `FIL_37` sirve `ruta_saludable` (12.ª tool MCP) y el mapa (`FIL_45`) expone los 9 perfiles de sensibilidad, incluidos `ciclista` y `movilidad_reducida`, tanto para colorear como para la ruta E3. |

## Ficheros

| Fichero | Qué |
|---|---|
| `export_gold_slices.py` | congela las 4 tablas Gold a `data/gold_slices/` (G1) |
| `build_grafo_madrid.py` | `grafo_madrid.json` — nodos+distrito, aristas, lookups |
| `build_prevision_animada.py` | `data/prevision_animada.parquet` — inferencia 24×3 de los 2 STGNN |
| `build_grafo_ruta.py` | `asistente/modelos/grafo_ruta.json` — artefacto de la 12.ª tool MCP (`FIL_37`) |
| `rutas.py` | enrutado saludable (`ruta()` / `mejor_hora()` / `pareto()`) + `mapa/rutas.json` |
| `build_mapa_animado.py` | `mapa/` (HTML + JSON) + `mapa_frames.png` |
| `assets/distritos_madrid.geojson` | 21 distritos (Bronce `barrios_distritos`) |
| `assets/ejes_madrid.geojson` | trazados **aproximados** de M-30 / Castellana / Gran Vía / A-2 / A-3 — solo contexto visual (`FIL_47`), no entran en el grafo |
| `assets/parques_madrid.geojson` | 16 parques grandes (subconjunto curado de `parques_jardines_madrid`, Bronce) |
| `PROGRESO_MAPA.md` | seguimiento milestone a milestone del entregable |

Tests: `tests/test_grafo_madrid.py`, `tests/test_prevision_animada.py`,
`tests/test_mapa_animado.py`, `tests/test_rutas.py` (bajo `tests/` porque el
CI no recorre `viz/`).
