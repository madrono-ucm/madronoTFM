---
kind: vic
title: "Memoria §7.1–7.3 — Resultados, métricas, comparativas (necesita salidas de ML)"
owner: Víctor
status: pending
depends_on: [ML Tier 1, ML Tier 2]
created_at: "2026-08-28"
---

## Secciones

§7.1 Logros y validación · §7.2 Métricas utilizadas · §7.3 Comparativas.

## Fuente técnica (se genera en la pista Sistema)

- `modelado/README.md` + `modelado/evaluation/` — métricas y estudios.
- Salidas MLflow (experimentos, tabla comparativa por modelo/horizonte).
- `doc/` de los tickets de ML (feature store, Tier 1 LightGBM, Tier 2 GNN,
  explicabilidad).
- `NEXT_STEPS.md` §4 (realidad de datos: ~14 días → ~550 snapshots a la
  entrega; holdout = últimos 3 días).

## Estructura a escribir (esperar a que existan 4–5 salidas reales)

- **§7.1** — la plataforma entrega, extremo a extremo: ingesta de N fuentes
  → lakehouse gobernado por GE → grafo urbano → **predicción multi-señal
  sobre el grafo** + asistente. Validación en tres ejes: calidad/consistencia
  de datos integrados; **capacidad predictiva de la fusión multi-señal
  frente a líneas base**; fidelidad de las respuestas del asistente a los
  datos.
- **§7.2** — Tabla 3. Métricas reales del pipeline `modelado/`:
  - regresión: MAE, RMSE, **skill score vs persistencia**, por horizonte
    (1/3/6 h) y por tipo de nodo;
  - clasificación de "episodio" (cruce de umbral OMS): precisión, recall,
    PR-AUC;
  - datos: nº de fuentes integradas, cobertura temporal, tasa de lotes
    rechazados por GE (usar el incidente `doc/072`–`077` como caso).
- **§7.3** — comparativas. **Decisión 8 pendiente** (`NEXT_STEPS.md` §5.7):
  - siempre: **baseline (persistencia/climatología) vs LightGBM vs GNN**,
    por horizonte;
  - explicabilidad: SHAP para LightGBM, importancia de aristas para el GNN
    (qué vecinos del grafo pesan);
  - **si se mantienen las ablaciones de §7.3**: fusión multi-señal vs
    modelo de una sola fuente; y "entrenar con todo Madrid pero evaluar solo
    con el sustrato europeo común (CAMS + AEMET + calendario)" para estimar
    la pérdida al portar a otra ciudad. Si se recortan, decirlo aquí y
    quitar la frase correspondiente del borrador.

## Qué cambia respecto al borrador

- El borrador de §7 está casi vacío. Aquí se escribe con datos reales.
- Ajustar §7.3 al alcance que fije la decisión 8.

## Aceptación

- §7.2 Tabla 3 rellena con métricas reales, no placeholders.
- §7.3 coherente con lo que `modelado/evaluation/` produjo realmente.
- La ventana corta de datos se nombra aquí y se remite a §7.4.
