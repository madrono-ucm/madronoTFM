---
kind: fil
title: "ruta_saludable — recomendador ambiental sobre el grafo (CONDICIONAL)"
owner: Filippos (interactive)
status: blocked
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_34]
milestone: M6
target: "2026-09-14 (si el gate se abre ~2026-09-08)"
---

## Gate — no empezar hasta que se cumpla

1. Esta rama (`FIL_31`) mergeada limpia, **y**
2. El núcleo del mapa (`FIL_34`) funcionando, a más tardar ~día 8 del
   calendario (≈ 2026-09-07).

Si no se cumple, este ticket **no entra** en la entrega y queda como trabajo
futuro con sustrato firme (el spine "map-only" es el entregable seguro).

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
