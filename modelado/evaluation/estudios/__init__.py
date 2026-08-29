"""Cuadernos de evaluación para la memoria §7 (ML_08).

`estudio_comparacion.py` -- funciones puras que consolidan las salidas de
Tier 1 (`train_gbt`) y Tier 2 (`train_stgnn`) en una tabla/figura por
estudio. `run_all.py` las orquesta contra los paneles reales y regenera los
artefactos de `modelado/evaluation/artifacts/estudios/`.

Estudios (decisión 8, `NEXT_STEPS.md` §5.7): se hacen el **1** (comparación
baseline vs GBT vs GNN) y el **2** (explicabilidad: SHAP + importancia de
aristas). Las ablaciones 3 y 4 (fusión multi-señal / "sustrato europeo
común") se **descartan para esta entrega** por tiempo -- documentado, no
omitido.
"""
