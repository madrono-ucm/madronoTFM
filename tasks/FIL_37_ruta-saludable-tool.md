---
kind: fil
title: "ruta_saludable — recomendador ambiental sobre el grafo"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_34]
milestone: M6
target: "2026-09-14"
---

## Cierre (2026-08-31) — 12.ª tool MCP

`viz/rutas.py` (PR #211) + **12.ª tool MCP `ruta_saludable`**:
`viz/build_grafo_ruta.py` → `asistente/modelos/grafo_ruta.json` (1,8 MB:
grafo + adyacencia + exposición prevista por día/hora + ruido por distrito +
lugares + perfiles). `asistente/ruta_saludable.py` — Dijkstra en **Python
puro** (sin `networkx`, sin Neo4j/Athena — autocontenido como
`asistente/athena.py`). Tool `ruta_saludable(origen, destino, perfil,
momento)` → `RutaSaludable` (contenedor con `output_schema`, `FIL_24`);
`momento` elige el día curado (por fecha exacta o día de la semana) y la
hora. Router `GET /ruta-saludable`. `server.py` a **12 tools**,
`test_mcp_tools`/`test_mcp_transport` a 12. `asistente/tests/test_ruta_saludable.py`
(11). Suite `asistente/`+`tests/` → **171 en verde**. `fiabilidad` topada
BAJA (§7.4, demostración de metodología, 3 días curados).

## Gate — ABIERTO (2026-08-31)

`FIL_31` mergeado (PR #209) + núcleo del mapa (`FIL_34`, PR #210) funcionando
el mismo día → el gate se cumple con 7 días de adelanto. El ticket entra.

## Estado (2026-08-31) — core hecho

`viz/rutas.py` + `tests/test_rutas.py` (6) + capa E3 en `viz/mapa/index.html`
+ `viz/mapa/rutas.json`. Ver "Resolución" abajo. **Pendiente**: la
envoltura como 12.ª tool MCP (artefacto vendorizado en `asistente/`).

## Resolución (2026-08-31)

- `viz/rutas.py`: `grafo_madrid.json` → `networkx` (componente conexa mayor,
  1.661/1.798 nodos). Coste de arista = `w_dist·(length_m/1000) + Σ_señal
  w_señal·exposición_norm`, con exposición por nodo/hora de
  `prevision_animada.parquet`. 4 perfiles (`general`, `ciclista`,
  `sensible_aire`, `sensible_ruido`).
- `ruta(o, d, perfil, dia, hora)` → ruta sana vs rápida + Δdistancia +
  reducción de exposición por señal. `mejor_hora(...)` barre la ventana.
  `pareto(dia, hora)` → puntos (Δdist %, reducción media %) para §7.
- Resultado §7 (miércoles cargado, 14 h): ciclista **+10 % distancia →
  +6,6 % reducción media**; general +2,2 %→+3,4 %; sensible_ruido
  +8,6 %→+5,6 %. El **O₃ apenas se puede esquivar** (contaminante regional,
  superficie suave — gap G4) — honesto en la memoria.
- Capa **E3** en el mapa: selector de 6 rutas (3 OD × general/ciclista),
  path sana (verde) vs rápida (gris) recalculada cada hora + readout.
- `w_noise` opera sobre el LAeq diario del distrito (gap G2).

## Alcance (si el gate se abre)

- **12.ª tool `ruta_saludable(origen, destino, ventana, perfil)`**
  (`perfil ∈ {ciclista, sensible_aire, sensible_ruido, general}`) +
  `GET /ruta-saludable` + `TraficoRutaSaludable(RespuestaAsistente-compat)`.
  - OD resueltos por coincidencia de texto sobre el grafo (geocodificación
    de dirección libre = encuadre).
  - Coste de arista = `w_dist·len + w_air·(NO₂+O₃) + w_noise·dB +
    w_traf·intensidad`, pesos por perfil. Interpolación de `FIL_33`.
    **Nota**: `w_noise` opera sobre el LAeq **diario del distrito** (única
    resolución disponible), no sobre ruido por arista.
  - Camino mínimo con `networkx` sobre `viz/grafo_madrid.*` (sin GDS).
  - Salida: ruta recomendada (corredores), su exposición prevista vs la ruta
    más rápida, **mejor hora de salida** en la ventana, y un "por qué"
    (aristas más costosas → importancia de aristas del STGNN que las explica).
- **Evaluación Pareto** (`§7`): ~50 pares OD, dispersión de (Δtiempo %,
  reducción de exposición %), healthy vs fastest, por perfil.
- **Caso ciclista**: una ruta con nombre, mapa + números.
- Capa de ruta interactiva en el mapa animado (E3 — ruta que "respira").

## Coste

Cero AWS.

## Entregable / progreso

Milestone **M6** (condicional) en `viz/PROGRESO_MAPA.md`.
