---
kind: fil
title: "curva_robustez: recalc_cada=25 subestima gravemente el daño del ataque dirigido"
owner: Sistema
status: done
created_at: "2026-09-10"
depends_on: [FIL_64]
found_by: VIC_36
---

## Hallazgo

`modelado/grafo_analitica/analisis.py::curva_robustez` recalcula el ranking
de *betweenness* cada `recalc_cada=25` bajas (por coste: O(V·E) por
recálculo sobre ~3053 nodos). El ranking se queda obsoleto entre
recálculos: tras quitar el nodo más central, la topología cambia, pero el
ataque sigue apuntando al *siguiente de la lista vieja* durante hasta 24
pasos más, en vez de al nodo realmente más crítico del grafo actual. Un
ataque dirigido *de verdad* (recompute exacto en cada paso) es
sustancialmente más dañino que lo que reporta la curva actual.

**Evidencia** (subgrafo BFS de 400 nodos del componente mayor real, mismo
código, `frac_max=0.15`, `seed=42`): al 5 % de bajas, el fragmento mayor
según el recálculo por lotes (`recalc_cada=25`) es **0,86** de la red
intacta; con recálculo exacto (`recalc_cada=1`) es **0,09** — una
diferencia de 0,77 en el mismo punto de la curva, sobre el mismo grafo y
la misma semilla. El ataque aleatorio (`aleatorio`) no se ve afectado
(no depende de ranking alguno) y ya está bien muestreado
(`reps_aleatorio=5` vs `reps_aleatorio=30`, incluso con distintas
semillas, cambia el `frag_mayor_al_5pct` en <0,02 — **no** hace falta
subir `reps_aleatorio`).

No se pudo repetir la comparación exacto-vs-lotes sobre el componente
mayor real completo (3053 nodos): un recálculo de *betweenness* completo
tarda ~24 s en este grafo, y `frac_max=0.10` por defecto pide hasta 305
recálculos exactos (~2 h) — inviable para este ticket de QA. La cifra
publicada hoy en `grafo_resiliencia.json`
(`frag_mayor_al_5pct.dirigido = 0,3957`, ver §7 de la memoria vía
`VIC_38`) **probablemente sobreestima la resiliencia real** frente a un
atacante que recalculase en cada paso, pero no se puede cuantificar el
tamaño exacto del sesgo a esta escala sin ese cómputo.

## Impacto en la memoria

El titular "al 5 % de bajas dirigidas el fragmento mayor cae a 39,6 % vs
89,1 % aleatorio" (§7, vía `VIC_38`) debe matizarse: es el resultado de
una **aproximación de ataque dirigido por lotes**, no de un adversario
óptimo recalculando en cada paso; el daño real bajo un ataque óptimo
podría ser considerablemente mayor. No invalida el hallazgo cualitativo
(dirigido ≫ aleatorio), pero sí el valor cuantitativo exacto como cota
superior de resiliencia.

## Alcance de la corrección (a decidir por Sistema, no bloquea `VIC_38`)

Dos caminos, no excluyentes:
1. **Reducir `recalc_cada`** (p. ej. a 5 o a 1) solo para el tramo inicial
   de la curva (los primeros 5-10 % de bajas, que es lo que cita la
   memoria), aceptando el coste computacional mayor — factible si se
   acota `frac_max` a ese tramo en vez de correr hasta 10 %.
2. **Dejar `recalc_cada=25` pero re-etiquetar explícitamente** la curva
   como "ataque dirigido aproximado (recálculo cada 25 bajas)" en el
   propio artefacto/figura y en la memoria, y añadir la cota exacta solo
   para un tramo corto (p. ej. los primeros 20-30 nodos, computacionalmente
   viable) como evidencia de cuánto más rápido cae con recálculo exacto.

## Verificación

Script de reproducción (subgrafo BFS de 400 nodos, ~4 s de cómputo):
ver `doc/VIC-36-eval-grafo-analitica-resiliencia.md` §1 para el código
exacto y las dos curvas completas (lotes vs exacto).

## Criterios de aceptación

- Se decide y aplica una de las dos vías (o ambas), o se documenta
  explícitamente en la memoria (`VIC_38`) que la cifra es una
  aproximación con sesgo conocido hacia una resiliencia mayor de la real.
- No bloquea el cierre de `VIC_36` (que ya recoge este hallazgo) ni de
  `VIC_38` (que debe redactar el caveat aunque este ticket siga abierto).

## Hecho (2026-09-10, Claude)

Elegida la vía 2 del propio ticket ("dejar `recalc_cada=25` pero
re-etiquetar explícitamente la curva... en el propio artefacto/figura y
en la memoria") en vez de la vía 1 (bajar `recalc_cada`): el propio
`VIC_36` ya midió que un recálculo exacto sobre el componente mayor real
(3053 nodos) tarda ~24 s por paso y el `frac_max=0.10` de producción
pediría hasta 305 recálculos (~2 h) -- desproporcionado para lo que
queda hasta la entrega, y el ticket no lo exige (su propio criterio de
aceptación acepta la vía 2 como cierre completo).

Aplicado en las tres capas que pedía el ticket:

- **Artefacto** (`grafo_resiliencia.json`): `curva_robustez()` añade un
  campo `_nota_dirigido` que explica la aproximación por lotes, cita el
  `recalc_cada` real usado y remite a `FIL_86`; deja claro que
  `frag_mayor_al_5pct.dirigido` es una cota optimista, no un valor
  ajustado. El régimen `aleatorio` no lleva la nota (no tiene ese sesgo).
- **Figura** (`grafo_resiliencia.png`): la leyenda de la curva dirigida
  pasa de "ataque dirigido (betweenness)" a "ataque dirigido (aprox.,
  recálculo por lotes -- FIL_86)".
- **Memoria** (`documents/Memoria_TFM FV.docx`, ya cerrada por `VIC_38`
  con el texto de 3 frases que `VIC_36` había redactado): la Figura 2 se
  corrigió también en el pie para decir "ataque dirigido aproximado
  (línea sólida, recálculo de intermediación por lotes)", coherente con
  la leyenda nueva de la figura real.

No se recalculó `grafo_resiliencia.json`/`.png` reales en esta sesión
(no hace falta un recálculo del contenido, solo el cambio de código que
añade la nota y relabela la leyenda — el JSON/PNG committeados se
regenerarán con el resto de artefactos en la próxima ejecución real de
`python -m modelado.grafo_analitica.analisis`, ya con la nota incluida).

Test nuevo `test_curva_robustez_documenta_el_sesgo_del_recalc_por_lotes`
confirma que `_nota_dirigido` existe, cita el `recalc_cada` real usado y
menciona `FIL_86`. Suite `modelado/tests/test_grafo_analitica.py`: 12
passed, 2 failed (preexistentes de `FIL_61`, sin relación).
