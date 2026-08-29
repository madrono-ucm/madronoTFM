# VIKT-01 — QA sweep de la memoria contra el repo (estado `ML_10`)

Pasada de solo lectura sobre `documents/Memoria_TFM FV.docx` (129 párrafos,
3 tablas, ~4 500 palabras) tras cerrar `ML_04`–`ML_10` (PRs #159–#168).
**No se editó el `.docx`** — esto es el informe que guía a `VIKT_02`–`VIKT_04`.

## Veredicto

La memoria está **estructuralmente sana y casi lista para entrega**. El
grueso de la reescritura de `VIC_*` (arquitectura real, Tabla 3 con modelos
reales, ablaciones de decisión 8 descartadas explícitamente, §7.4/§7.5)
sigue siendo correcto. **No hay ningún dato inventado.** Pero hay dos
cosas al borde de severidad alta y varias de freshness:

1. **§6.7 dice «seis herramientas»** y describe la previsión como
   condicional («cuando el modelo… esté disponible») — `ML_09` la hizo:
   son **siete** y la previsión **ya se sirve**. → `VIKT_02`.
2. **§7.2 Tabla 3, filas de tráfico**, no se reproducen con
   `modelado/evaluation/estudios/run_all.py` tal como está: la memoria usa
   el *scope* `grafo-lugares` (1 813 puntos, `doc/ML-03`/`doc/ML-05`) y el
   `run_all.py` re-entrena LightGBM de tráfico sobre el panel completo
   (~4 700 puntos), dando cifras distintas. Los números de la memoria son
   correctos; lo que falla es la ruta de reproducibilidad. → `VIKT_03`.

## Grep de términos obsoletos — todos legítimos

| término | dónde aparece | ¿residuo? |
|---|---|---|
| Kafka / Avro / Flink / KSQL / streaming | §4.1, §5.2, §5.3, §6.3, §6.4, §7.4 (como "no se construyó / se sustituye por…"), §7.5 (línea futura), §8 Anexo B (glosario) | **No** — todos correctos |
| Delta Lake / Delta | §5.2, §5.3 (como "sustituye a…"), §7.5 (futura), §8 glosario | **No** |
| Power BI | §5.2, §6.7, §7.5 (como "no se construyó / futura") | **No** |
| Google / populartimes | §6.8 (como "se evaluó y se descartó") | **No** |
| Sentinel-5P | §7.5 (futura) | **No** |
| "esquemas Avro" | §8 Anexo C ("Repositorio de código, esquemas Avro y cuadernos…") | **Sí, residuo menor** — no hay Avro; es `normalize_record` + `schema_version`. → `VIKT_04` |

## Tabla de discrepancias

| # | Sección | Afirmación en la memoria | Realidad (fuente) | Severidad | Arreglo | Ticket |
|---|---|---|---|---|---|---|
| 1 | §6.7 | «un agente MCP con **seis herramientas reales** —calidad del aire, tráfico cercano, afluencia estimada, disponibilidad de aparcamiento, eventos cercanos y opciones de movilidad—» | **7 tools**; falta `calidad_aire_prevista` (`asistente/README.md`, `doc/ML-09`, `server.py` registra 7) | **alta** | «siete herramientas», añadir la de previsión a la lista | `VIKT_02` |
| 2 | §6.7 | «—cuando el modelo de calidad del aire de `modelado/` **esté disponible**— su previsión a corto plazo» | El modelo se sirve ya vía ONNX; `calidad_aire_prevista` verificada en vivo contra Athena (O₃ Retiro 97 → h6 30) (`doc/ML-09`) | **alta** | quitar el condicional; describir la tool de previsión (ancla al último dato de Gold, fiabilidad por `data_completeness`) | `VIKT_02` |
| 3 | §7.2 Tabla 3 | Tráfico LightGBM: h1 `0,083 / 0,182 / 0,38`; h3 `0,090 / 0,196 / 0,63`; h6 `0,091 / 0,199 / 0,78` | Esas cifras son de `doc/ML-03` (*scope* `grafo-lugares`, n≈1 813). `estudios/comparacion_todos.csv` (`run_all.py`, panel completo, n≈321 624) da `0,075 / 0,081 / 0,081` y skill `0,37 / 0,61 / 0,76` | **media-alta** | apuntar el LightGBM de tráfico de `run_all.py` a `panel_trafico_grafo.parquet` y regenerar `comparacion_todos.csv` para que cuadre con la Tabla 3 y con el STGNN (mismo conjunto de nodos) | `VIKT_03` |
| 4 | §7.2 Tabla 3 | Filas de **STGNN de tráfico** (h1 `0,097/0,184/0,39` …) | Correctas (`doc/ML-05`), pero `comparacion_todos.csv` **no las contiene** (último `run_all` fue `--sin-gnn` para tráfico) | media | correr `run_all.py --con-gnn-trafico` una vez y commitear, o citar `doc/ML-05` en el pie de tabla | `VIKT_03` |
| 5 | §6.1 / §7.1 | «integra **24 fuentes**… **catorce** … / 24 fuentes abiertas (**14 en producción continua**)» | 24 módulos de captura ✓; pero **16 productores Lambda desplegados** ahora (`infra/terraform/lambda.tf` `local.producers`: +`emt_incidencias`/`parques_jardines`/`ser_calles` por FIL_03/04/05, −`afluencia_lugares` por FIL_06 → 14+3−1) | media | «16 en producción continua» (y revisar el reparto 24 = 16 continuas + 8 de referencia/estáticas) | `VIKT_03` |
| 6 | §7.3 | «los cuadernos de evaluación de `modelado/` (que las ejecutarían) **aún sin construir**» | `ML_08` los construyó: `modelado/evaluation/estudios/run_all.py` (`doc/ML-08`) | media | las ablaciones 3/4 se mantienen descartadas por **decisión 8** (tiempo), pero el motivo ya no es "sin construir" — reformular | `VIKT_03` |
| 7 | §7.3 / §7.4 | §7.3 «~2,5 semanas hasta el cierre»; §7.4 «entre **tres y cuatro semanas** de histórico» | Datos: 14 ago → panel hasta ~28 ago ≈ **2 semanas** de histórico entrenable; hasta la entrega (17 sep) ≈ 4,7 semanas | media | armonizar: los modelos se entrenan sobre ~2 semanas; a la entrega habrá ~4 (si el nightly de `ML_10` corre) | `VIKT_03` |
| 8 | §5.5 | «MLflow para el versionado y el registro, y con Evidently para vigilar la deriva **en producción**» | MLflow: backend **SQLite local**, registro con alias **`@champion`** (no *stages*), coste 0 (`doc/ML-04`). Evidently: informe **bajo demanda** (PSI+KS+`DataDriftPreset`), no un watchdog en vivo (`doc/ML-06`) | media | precisar backend SQLite + `@champion`; Evidently = informe de deriva bajo demanda; añadir ONNX (paridad + `CONTRATO.md`) y **reentrenamiento nocturno** (`ML_10`, cron, coste 0) | `VIKT_02` |
| 9 | §5.5 | «los modelos se exportan a ONNX para una ejecución portable» | Cierto para **LightGBM** (4 `.onnx`, `doc/ML-07`); el **STGNN no** exporta (bloqueado por `torch.export`) | baja | matizar "los forecasters de árbol"; STGNN→ONNX a §7.5 | `VIKT_02` / `VIKT_03` |
| 10 | §7.4 | (no aparece) | Falta: la **curva de backtest incremental** de `ML_10` (skill h6 de `calidad_aire` sube ~0,63→0,80 entre 22 y 28/8, bache real 24–25/8) como evidencia directa de "ventana corta, sin converger" | media | añadir un párrafo con la curva y remitir a `modelado/evaluation/artifacts/backtest/skill_vs_fecha_calidad_aire.png` | `VIKT_03` |
| 11 | §7.4 | (no aparece) | Falta: la **cota de paridad ONNX** de `ML_07` (error medio ~0,1 % de la escala; cola p99 por el convertidor de LightGBM en el límite de los *splits*, documentada) | baja | media frase en §7.4 o §5.5 | `VIKT_02` / `VIKT_03` |
| 12 | §7.4 | (no aparece) | Falta: el **resultado de deriva** de `ML_06` (con ~2 semanas es ilustrativo; solo las features de día de la semana "derivan" = artefacto de partición; la señal es estable) | baja | media frase en §7.4 | `VIKT_03` |
| 13 | §7.5 | (no aparece) | Faltan como líneas futuras: **STGNN→ONNX** (→ tool `afluencia_prevista`), y el **join de meteo/previsión AEMET + festivos** en el feature store (`ML_01` lo dejó de esqueleto) | media | dos viñetas nuevas en §7.5 | `VIKT_03` |
| 14 | §8 Anexo C | «Repositorio de código, **esquemas Avro** y cuadernos de evaluación» | No hay Avro (`normalize_record` + `schema_version`); el anexo debería ser la **reproducibilidad del modelado** | baja | Anexo C → un comando por tabla/figura de §7, layout de `modelado/`, `mlflow ui`, la línea de cron | `VIKT_04` |

## Material de `ML_04`–`ML_10` no mencionado (y dónde va)

| material | ticket | fuente | destino en la memoria |
|---|---|---|---|
| MLflow registry con `@champion`, backend SQLite | `ML_04` | `doc/ML-04` | §5.5 |
| Evidently: PSI+KS + `DataDriftPreset`, resultado real | `ML_06` | `doc/ML-06` | §5.5 (mecanismo), §7.4 (resultado) |
| ONNX: 4 `.onnx`, test de paridad, `export/CONTRATO.md` | `ML_07` | `doc/ML-07` | §5.5, §7.4 (cota), Anexo C |
| `estudios/run_all.py` como origen único de §7.1–7.3 | `ML_08` | `doc/ML-08` | §7.2/§7.3 (ya casi), Anexo C |
| Tool `calidad_aire_prevista` + `GET /calidad-aire-prevista`, verificada en vivo | `ML_09` | `doc/ML-09` | §6.7, §4.1 (bucle cerrado) |
| Backtest incremental (curva skill vs fecha) + reentrenamiento nocturno (cron, coste 0) | `ML_10` | `doc/ML-10`, `infra/OPERACION.md` | §5.5, §7.4, Anexo C |

## Comprobaciones que salieron bien (no tocar)

- **Tabla 3, filas de calidad del aire** (6): cuadran al céntimo con
  `comparacion_todos.csv` y `doc/ML-03`/`doc/ML-05`.
- **§7.3 explicabilidad**: los ejemplos de importancia de arista
  (O₃ 28079035 ← 28079049; tráfico "un único tramo contiguo") son reales
  (`doc/ML-05`).
- **§7.3 ablaciones**: descartadas de forma explícita y con motivo — solo
  hay que actualizar el "aún sin construir" (disc. #6).
- **§5.4 / Tabla 2 (costes)**: nada de `ML_04`–`ML_10` añade coste (SQLite,
  `cron`, `onnxruntime` en CPU) — la tabla sigue válida.
- **§5.2 / §5.3 / §6.x**: la pila real (Lambda/EventBridge, Glue+Athena,
  Partition Projection, Neo4j, sin Kafka/Delta/streaming) está bien contada.
- **§7.4**: las 7 limitaciones existentes siguen vigentes; se **añade**, no
  se corrige.

## Nota de código (fuera del `.docx`)

`infra/terraform/lambda.tf:16` — el comentario dice «`local.producers`: una
entrada por función Lambda (**14**, …)»; ahora son **16**. Arréglese junto
con los tickets `VIKT_*` (trivial, no bloquea nada).
