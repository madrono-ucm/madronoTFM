---
kind: vic
title: "Memoria §7.1–7.3 — Resultados, métricas, comparativas (necesita salidas de ML)"
owner: Víctor
status: done
done_by: "Claude (Sonnet 5)"
done_at: "2026-08-29"
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

## Hecho (29/8)

§7.1–7.3 reescritas en `documents/Memoria_TFM FV.docx` con datos reales
verificados (no de la nota del ticket: releídos directamente de
`modelado/evaluation/artifacts/tier1_*.csv` y `doc/ML-05-...md`). Tabla 3
reconstruida de cero (era una tabla "eje → métrica" genérica de 2
columnas; ahora es una tabla real de 6 columnas con MAE/RMSE/skill por
fuente, horizonte y modelo, indicando explícitamente contra qué línea
base se mide cada skill score, porque LightGBM y el STGNN no siempre se
miden contra la misma). §7.3 incluye la explicabilidad real de ambos
modelos (SHAP / importancia de aristas) y una decisión explícita: las
ablaciones de la "decisión 8" (`NEXT_STEPS.md`) se descartan para esta
entrega por tiempo (`ML_08`, que las produciría, sigue sin construir) y
se documentan como futura línea, no como omisión — recomiendo revisar
esta decisión con el usuario si aparece tiempo antes del 17/9.

De paso, corregido un hallazgo de la propia auditoría: la Tabla 2 (§5.4,
`VIC_01`) todavía tenía una fila real de coste ("Live popular times / Pay
per use Google Api ~29€/mes") que databa de antes de que se descartara
Google Maps — corregida a 0 € / señal derivada, coherente con el resto
de la sección ya reescrita.
