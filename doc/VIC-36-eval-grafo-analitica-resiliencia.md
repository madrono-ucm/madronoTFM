# VIC_36 — Evaluación de la analítica de resiliencia del grafo (FIL_64, 2026-09-10)

QA de código + validación numérica de `modelado/grafo_analitica/analisis.py`
(funciones de resiliencia añadidas en `FIL_64`: puntos de articulación,
puentes por línea, k-core, curva de robustez), contra el grafo real
(`grafo/exportar_grafo.cargar()`, componente mayor de `CONECTADO_CON` =
3053 nodos / 3641 aristas).

## 1. Corrección de las funciones — 4/5 bien, 1 con un sesgo real (⚠️ → `FIL_86`)

- **`puntos_de_articulacion`** ✅ — `nx.articulation_points` sobre la
  componente mayor, correcto. El orden (`filas.sort(key=... frac_red_en_
  fragmento_mayor)`, ascendente) pone primero el nodo cuya eliminación deja
  el **fragmento mayor más pequeño**, es decir el de más daño primero —
  es el criterio que el propio docstring promete ("fragmento mayor más
  pequeño primero" = más dañino primero). Correcto.
- **`puentes_por_linea`** ✅ — `nx.bridges` + agregación por `(modo,
  linea)` verificados con el test sintético (línea con triángulo → 0
  puentes; líneas en cadena → `frac_puentes=1.0`). Correcto.
- **`kcore_resumen`** ✅ — `nx.core_number` tras `remove_edges_from(nx.
  selfloop_edges(H))`; sobre el grafo real da `k_max=2`, coherente con una
  red modelada como líneas encadenadas + algunos triángulos de
  intercambiadores.
- **`curva_robustez` — ataque aleatorio** ✅ — `reps_aleatorio=5` es
  suficiente: comparado contra `reps_aleatorio=30` con 5 semillas
  distintas sobre un subgrafo de 400 nodos, `frag_mayor_al_5pct.aleatorio`
  varía <0,02 entre 5 y 30 repeticiones. No hace falta subir el valor.
- **`curva_robustez` — ataque dirigido, `recalc_cada=25`** ⚠️ **sesgo real,
  cuantificado**. El ranking de *betweenness* se recalcula solo cada 25
  bajas; entre recálculos, el ataque sigue una lista que ya no refleja la
  topología actual. Comparación directa sobre un subgrafo BFS de 400 nodos
  del componente mayor real (mismo código, `frac_max=0.15`, `seed=42`):

  | recálculo | `frag_mayor_al_5pct` (dirigido) |
  |---|---|
  | por lotes (`recalc_cada=25`, el valor de producción) | 0,8625 |
  | exacto (`recalc_cada=1`) | 0,0925 |

  Diferencia de **0,77** en el mismo punto de la curva. No se pudo repetir
  la comparación sobre el componente mayor completo (3053 nodos): un
  `betweenness_centrality` completo tarda ~24 s ahí, y el `frac_max=0.10`
  de producción pediría hasta 305 recálculos exactos (~2 h), inviable para
  esta QA. Abierto `FIL_86` con la evidencia completa y dos vías de
  arreglo (bajar `recalc_cada` para el tramo que cita la memoria, o
  re-etiquetar la curva como aproximada). **No bloquea el cierre de este
  ticket ni de `VIC_38`**, pero sí matiza cuánto se puede afirmar con la
  cifra actual — ver veredicto más abajo.

## 2. Determinismo — ✅ confirmado

`resiliencia_transporte(G_conn, nombres)` ejecutado dos veces seguidas
sobre el grafo real (mismos `seed=42` por defecto en `betweenness` y en el
`random.Random` del muestreo aleatorio): **JSON byte-idéntico**
(`json.dumps(..., sort_keys=True)` idéntico carácter a carácter en ambas
corridas). El artefacto committeado (`grafo_resiliencia.json`,
`n_puntos_articulacion=683`, `puentes=740` (20,3 %), `k_max=2`,
`frag_mayor_al_5pct={dirigido: 0.3957, aleatorio: 0.8908}`) es reproducible
tal cual con `resiliencia_transporte()`. No se pudo verificar vía el
`main()` completo del módulo (`python -m modelado.grafo_analitica.
analisis`) porque **este `.venv` tiene `networkx==2.6.3`**, que no expone
`nx.community.louvain_communities` (falla en `comunidades_vs_barrios`,
antes de llegar a la resiliencia) — es el mismo problema ya rastreado en
`FIL_61` ("networkx sin pin — louvain_communities falla en esta EC2"), no
un hallazgo nuevo; verificado llamando a `resiliencia_transporte()`
directamente, que no depende de Louvain.

## 3. Caveat `k_max=2` / "1 viaje por línea" — ✅ correcto y bien redactado

Confirmado en el código: `grafo/relaciones.py::conectado_con` solo emite
pares consecutivos dentro del mismo `route_id`, para **un único viaje
representativo por línea** (`direction_id="0"`, o el primero disponible).
El productor `ingesta/capturas/crtm_red_transporte_madrid.py` lo confirma
en su propio docstring ("Esquema mínimo elegido... se elige un único viaje
(`trip_id`) representativo... sin necesitar modelar calendarios,
frecuencias ni el resto de viajes"). La afirmación de la `_nota` en
`resiliencia_transporte` es exacta y, releída como la leería alguien ajeno
al proyecto, dice explícitamente "no como diagnóstico operativo de la
EMT/Metro reales" — no hay riesgo real de sobre-interpretación si el texto
de la memoria (`VIC_38`) reproduce esa misma nota o algo equivalente.

## 4. Cobertura de tests — ✅ con una nota menor

Las 5 pruebas de `ResilienciaTests` pasan (`pytest modelado/tests/
test_grafo_analitica.py -k "Resiliencia or Artefactos"` → 6/6 verdes,
incluye `ArtefactosTests`). El grafo sintético (A-B-C-D-E-F + triángulo
C-C1-C2) cubre: punto de articulación (D), puentes vs línea sin puentes
(triángulo), k-core no trivial, monotonía de la curva y agregación. **No
cubre explícitamente** un grafo ya fragmentado en el input (varias
componentes antes de cualquier baja) ni un nodo de grado 1 aislado como
caso límite propio — ambos funcionan por construcción (`_componente_mayor`
siempre opera sobre la componente mayor, ignorando el resto por diseño,
documentado en su docstring), pero no hay una aserción explícita que lo
verifique. Menor, no bloqueante — nota dejada aquí en vez de abrir un
`FIL_*` para una cobertura de test adicional que no cambia comportamiento.

## 5. Figura `grafo_resiliencia.png` — ✅ legible en B/N

Inspeccionada visualmente: la curva de robustez usa **línea sólida roja**
para el ataque dirigido y **línea discontinua azul** para el aleatorio —
distinguibles sin depender del color (estilo de línea, no solo tono).
Ejes con etiquetas y unidades (`% de paradas eliminadas` / `fragmento
mayor / red intacta`), leyenda legible, título con el ticket de origen
(`FIL_64`). Los otros dos paneles (puntos de articulación, k-core) también
tienen ejes y títulos claros.

## Veredicto

**Publicable en §7 con una condición**: los puntos 2-5 están verificados y
son sólidos — el hallazgo cualitativo (existen puntos de articulación
reales, la red modelada es poco mallada, el ataque dirigido es
sustancialmente peor que el aleatorio, todo reproducible y bien
caveado sobre el alcance de `CONECTADO_CON`) se sostiene. **El valor
numérico exacto "39,6 % al 5 % de bajas dirigidas" no debe presentarse
como una cota ajustada** — es una aproximación por lotes que el punto 1
demuestra que puede subestimar el daño real de forma sustancial. Texto
propuesto para `VIC_38` (2-3 frases):

> *Un ataque dirigido a las paradas de mayor intermediación fragmenta la
> red mucho más rápido que un fallo aleatorio equivalente: al 5 % de
> bajas, el fragmento mayor cae a un 39,6 % de la red intacta frente a un
> 89,1 % bajo fallo aleatorio (Fig. X). Esta cifra usa un recálculo de
> intermediación por lotes (cada 25 bajas) por coste computacional, una
> aproximación estándar en el estudio de robustez de redes; un ataque que
> recalculase el objetivo en cada paso sería probablemente más dañino
> todavía, así que el 39,6 % es una cota optimista de la resiliencia real,
> no un valor ajustado. El hallazgo cualitativo — la red modelada, con un
> único viaje representativo por línea (véase 5.3/6.6), es intrínsecamente
> poco mallada (k_max=2, un 20 % de tramos son puentes sin alternativa) —
> se sostiene independientemente de esta aproximación.*

## Hallazgos abiertos

- `FIL_86` — sesgo cuantificado de `recalc_cada=25` en `curva_robustez`
  (ver punto 1). No bloqueante para `VIC_38`.
