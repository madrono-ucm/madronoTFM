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

### Controles

- **día**: 3 días curados de agosto 2026 (data-driven: miércoles normal /
  domingo tranquilo / miércoles cargado).
- **horizonte**: ahora / +1h / +3h / +6h (afecta solo a la métrica *tráfico*).
- **métrica**: salud (por defecto) · tráfico · NO₂ · O₃.
- **modelo vs persistencia (E2)**: colorea por la divergencia STGNN(h1) −
  persistencia; el marcador de *skill* compara ambos contra el valor real.
- **play / slider**: bucle de 24 h.
- **panel derecho**: pestaña *distritos* (pulso: 21 distritos ordenados por
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
| **cyclist / movilidad reducida routing** | encuadre — el sustrato existe (grafo + atributos), la herramienta sería `FIL_37` (`ruta_saludable`, condicional). |

## Ficheros

| Fichero | Qué |
|---|---|
| `export_gold_slices.py` | congela las 4 tablas Gold a `data/gold_slices/` (G1) |
| `build_grafo_madrid.py` | `grafo_madrid.json` — nodos+distrito, aristas, lookups |
| `build_prevision_animada.py` | `data/prevision_animada.parquet` — inferencia 24×3 de los 2 STGNN |
| `build_mapa_animado.py` | `mapa/` (HTML + JSON) + `mapa_frames.png` |
| `PROGRESO_MAPA.md` | seguimiento milestone a milestone del entregable |

Tests: `tests/test_grafo_madrid.py`, `tests/test_prevision_animada.py`,
`tests/test_mapa_animado.py` (bajo `tests/` porque el CI no recorre `viz/`).
