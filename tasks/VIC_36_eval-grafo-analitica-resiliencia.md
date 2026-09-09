---
kind: vic-eval
title: "Evaluación de la analítica de resiliencia del grafo (FIL_64) — corrección y caveat para la memoria"
owner: Claude (QA)
status: pending
created_at: "2026-09-09"
depends_on: [FIL_64]
---

## Contexto

FIL_64 extendió `modelado/grafo_analitica/analisis.py` (FIL_52) con 5
funciones de resiliencia estructural sobre `CONECTADO_CON` (`networkx`
offline sobre `grafo/_data/grafo_urbano.json.gz`): puntos de articulación,
puentes por línea, descomposición k-core y curva de robustez (ataque
dirigido vs aleatorio). Artefactos: `grafo_resiliencia.{json,png}`.

Resultados reportados: 683 puntos de articulación, 740 puentes (20% de las
aristas), `k_max=2`, y al 5% de bajas dirigidas el fragmento mayor cae a
39,6% vs 89,1% aleatorio.

## Alcance — revisión de código + validación de los hallazgos

1. **Corrección de las funciones.**
   - `puntos_de_articulacion`: usa `nx.articulation_points` sobre la
     componente mayor; el "daño" (`nodos_desgajados`,
     `frac_red_en_fragmento_mayor`) se calcula quitando el nodo y midiendo
     componentes. ¿El orden (fragmento mayor más pequeño primero) es el
     criterio deseado?
   - `puentes_por_linea`: `nx.bridges` + agregado por `(modo, linea)`.
     Revisar `frac_puentes` y `lineas_sin_redundancia`.
   - `kcore_resumen`: `nx.core_number` tras quitar self-loops.
   - `curva_robustez`: betweenness recalculado por lotes (`recalc_cada=25`)
     — ¿la aproximación por lotes distorsiona la curva frente a recalcular
     en cada baja? Comparar con un recálculo total en un subgrafo pequeño.
     El baseline aleatorio: `reps_aleatorio=5`, ¿suficiente?
2. **Determinismo.** `seed=42` en betweenness y en el shuffle aleatorio.
   Re-ejecutar `python -m modelado.grafo_analitica.analisis` y confirmar que
   `grafo_resiliencia.json` sale byte-idéntico (o solo cambia por
   float-precision).
3. **El caveat `k_max=2` / "1 viaje por línea".** `grafo/relaciones.py::
   conectado_con` solo conserva un viaje representativo por línea
   (`direction_id='0'`, primero). El `_nota` de `resiliencia_transporte` lo
   explica. Validar que:
   - la afirmación es correcta (leer `conectado_con` + el productor
     `crtm_red_transporte_madrid.py`),
   - el caveat está redactado para que un lector de la memoria no
     sobre-interprete los 683 puntos de articulación como un diagnóstico de
     la EMT/Metro reales.
4. **Tests** (`modelado/tests/test_grafo_analitica.py::ResilienciaTests`):
   el grafo sintético (2 líneas + triángulo) — ¿cubre los casos límite
   (grafo ya fragmentado, nodo de grado 1, línea sin puentes)?
5. **La figura** `grafo_resiliencia.png`: legible, ejes etiquetados, las dos
   curvas distinguibles en B/N (para impresión de la memoria).

## Criterios de aceptación

- Puntos 1-5 revisados; discrepancias de método → `FIL_*`.
- Veredicto claro: ¿los hallazgos de resiliencia son publicables en §7 tal
  como están, o necesitan más matices?
- Texto propuesto (2-3 frases) para la memoria, coordinado con `VIC_38`.
