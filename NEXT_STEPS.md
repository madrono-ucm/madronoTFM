# Plan de cierre — hacia el 17 de septiembre de 2026

Roadmap priorizado, escrito el 25/8/2026 tras la revisión de arquitectura
de las tareas 083-084 (ver [`PROGRESS.md`](PROGRESS.md) y
[`PLATFORM_SCHEMA.md`](PLATFORM_SCHEMA.md)). Quedan **~3.5 semanas** hasta
la entrega. Prioridades ordenadas por urgencia real, no por orden de
aparición en el repositorio — la número 1 es más urgente que Google Maps lo
fue nunca.

No sustituye al reparto por pista de [`PLAN.md`](PLAN.md#reparto-sin-conflictos)
— cada ítem indica a qué pista pertenece (Sistema / Memoria / Ambos).

---

# Estado a 28/8 — Fundación de datos y decisiones críticas para el cierre

Sesión del 28/8: chequeo de salud de **todas** las fuentes Madrid integradas
+ rastreo del código/docs de datapoints planificados pero ausentes, hecho
porque la fase de ML del TFM (objetivo de la memoria §3.2: *"entrenar
modelos predictivos de afluencia, congestión y calidad del aire"*) necesita
una fundación de datos sólida y completa **antes** de diseñar nada de ML.
Los arreglos de fundación se han convertido en tickets `FIL_*`
(`tasks/FIL_00_README.md`) — fuera de la cola del demonio, para trabajarlos
de forma interactiva.

## 1. Qué funciona hoy (verificado contra AWS real)

**14 productores continuos, todos con Lambda + EventBridge Scheduler + Glue
Bronze→Silver→Gold, última ejecución en verde:** `trafico`, `calidad_aire`,
`meteorologia`, `bicimad`, `aparcamientos`, `transporte_publico_emt`,
`ruido`, `agenda_eventos`, `bluesky_menciones`, `cartelera_cines_estrenos`,
`cams_calidad_aire`, `aemet_avisos` — Bronze fresco (horario o diario según
cadencia), Gold consultable en Athena. Puertas de calidad Great Expectations
reales en cada `bronze_to_silver` (`procesamiento/silver_gold/*/ge_suite.py`,
informes en `silver/_quality_reports/`).

## 2. Gaps de fundación de datos → tickets `FIL_*`

| Ticket | Problema | Impacto |
|---|---|---|
| `FIL_01` | `aemet_prevision` silver→gold **falla en producción** ("Failed to delete key"); Gold con 4 filas sin refrescar | Perdemos la previsión meteo como feature/contexto |
| `FIL_02` | Los 3 productores de la tarea 090 (`emt_incidencias`, `parques_jardines`, `ser_calles`) **solo tienen código de muestra** — sin `lambda_handler`, sin Bronze | Prerrequisito de FIL_03/04/05 |
| `FIL_03` | `emt_incidencias` sin desplegar | Señal de disrupción para `opciones_movilidad` y para ML (corredores afectados) |
| `FIL_04` | `parques_jardines` sin desplegar; **no hay ni un `:Lugar` de tipo parque en el grafo** | El caso de uso "paseo por el parque" de la memoria no tiene datos |
| `FIL_05` | `ser_calles` sin desplegar | Aparcamiento en calle (capacidad estática); posible mejora de `disponibilidad_aparcamiento` |
| `FIL_06` | **`afluencia_lugares` está muerto**: 100% Google Maps `populartimes`, sin clave posible, muestra `is_mock`, Gold con **0 filas**. Las Lambda/Glue "tienen éxito" con entrada mock y ocultan el hueco | **Es la capacidad estrella de la memoria** *("¿merece la pena ir a un lugar?")*. Sin ella el TFM es débil |
| `FIL_07` | `transporte_publico_emt` captura **1 sola parada** ("71") — límite de diseño del productor, no de la fuente | Señal EMT pobre para asistente y ML |

Fuentes descontinuadas / net-new (no son bug, son decisión — ver §5):
`aforos_peatones_bicicletas` (fuente municipal congelada 2024-06-30, solo
histórico); "SER. Tiques de aparcamiento" (ocupación en vivo, dataset aparte
no integrado); recarga de VE, plazas PMR, infraestructura ciclista,
observación por satélite (Copernicus/Sentinel) — todas **nombradas** en la
memoria o el radar de `doc/090`, ninguna construida.

## 3. Brecha memoria ↔ realidad (arquitectura descrita vs construida)

La memoria (§5) describe una pila que **en varios puntos no es la que se ha
construido**. Esto ya está señalado en `PLAN.md` (bloqueador 3) pero aquí va
el mapa completo:

| Componente en la memoria | Estado real |
|---|---|
| Apache Kafka + Kafka Connect + registro Avro | **No construido.** `infra/terraform/kafka.tf` existe pero se excluyó del `apply` a propósito (tarea 042). En su lugar: Lambda + EventBridge Scheduler |
| Ruta caliente Flink/KSQL, ventanas en streaming | **No construido.** No hay ruta caliente ni procesamiento en streaming en absoluto |
| Delta Lake (tablas Delta en 3 capas) | **No construido.** Parquet + catálogo Glue + Athena Partition Projection |
| Spark batch sobre Silver | Construido como **Glue** (Spark por debajo) ✓ |
| Grafo urbano en Neo4j desde Gold | Construido ✓ (AuraDB Free, cargado; 9430 nodos) |
| **MLOps: MLflow + Evidently + ONNX** | 🟡 **mayoría hecha (29/8)** — `modelado/`: MLflow tracking+registry (`ML_04`, backend SQLite) ✓, Evidently drift (`ML_06`) ✓, export ONNX (`ML_07`) ⬜ |
| Cuadro de mando Power BI + modelo semántico DAX | **No construido** |
| Asistente FastAPI + agente MCP | Construido ✓ (6 tools con lógica real) |
| Puertas de calidad Great Expectations | Construido ✓ (por dataset) |
| Cuadernos de evaluación (Anexo C, §7) | **No construidos** |

## 4. La realidad de los datos para ML

El demonio de ingesta lleva funcionando en continuo **desde el 2026-08-14**.
Bronze no tiene nada anterior. Profundidad real por tabla Gold (consultado
en Athena el 28/8):

| Tabla | Filas | Cobertura temporal |
|---|---|---|
| `trafico_por_punto_hora` | 1.45M | **14 días** horarios, ~4300 puntos |
| `calidad_aire_..._contaminante_hora` | 37k | **14 días** horarios, ~24 estaciones |
| `meteorologia_..._magnitud_hora` | 24k | **15 días** horarios |
| `bicimad_por_estacion_hora` | 218k | **19 días** horarios |
| `ruido_...` | 620 | 5 días |
| `aforos_peatones_bicicletas` | 1971 | **1 día** (2024-06-30, fuente congelada) |
| `afluencia_lugares_...` | **0** | — |

Implicación: solo cabe un modelo de **horizonte corto** (predecir 1–3 h
vista desde lags recientes + calendario + meteo + vecinos de grafo), con
holdout temporal (p.ej. últimos 3 días) y comparación contra líneas base
(persistencia, climatología horaria). **No hay datos para patrones
estacionales/diarios largos** — eso pasa a ser una limitación explícita de
§7.4. Los estudios de ablación que describe §7.3 (fusión multi-señal vs
fuente única; "solo sustrato europeo común") sí son viables con esta
ventana.

## 5. Decisiones tomadas (28/8, con Filippos)

1. **`afluencia_lugares`** → **señal derivada** (metodología de la tarea 089:
   lugar → sensores `PROXIMO_A` → tráfico+ruido+bici+aire), materializada
   como serie temporal Gold horaria. Es un target/feature de ML de primer
   nivel. Fórmula documentada como aproximación, igual que `indice_calidad`.
   → `FIL_06`.

2. **Memoria §5–§6** → **reescribir a la arquitectura real** (Lambda +
   EventBridge + Glue + Athena + Neo4j + FastAPI/MCP) como decisión de
   diseño justificada a coste 0 (§5.4 ya lo respalda). Kafka/Flink/Delta,
   Power BI y satélite → §7.5 Futuras líneas. La narrativa lambda
   "caliente/fría" solo se mantiene admitiendo que la ruta caliente no se
   implementó. → tickets `VIC_*`.

3. **Modelo ML — es el elemento central del TFM.** Prioridad nº 1: una
   **arquitectura de mejores prácticas** en `modelado/` (feature store sin
   fugas → CV temporal → líneas base → MLflow tracking+registry → Evidently
   → export ONNX). Sobre ella:
   - **Tier 1** — forecasters LightGBM multi-horizonte (1/3/6 h) para
     **calidad del aire, congestión de tráfico y afluencia derivada** + un
     clasificador de "episodio" por target. SHAP.
   - **Tier 2 (el "wow")** — **GNN espacio-temporal** sobre el grafo Neo4j,
     multi-tarea (AQ + congestión + afluencia), multi-horizonte. Importancia
     de aristas para explicabilidad. Alinea con "redes neuronales de grafos"
     (memoria §2/§5.2).
   - **Tier 4** — tool del asistente `*_prevista` servida desde ONNX;
     reentrenamiento nocturno programado; backtest incremental según se
     acumulan datos.
   Modelo entrenado con ~14 días (→ ~550+ snapshots para la entrega): se
   acepta como demostración de metodología; ventana corta = limitación
   declarada de §7.4. Holdout = últimos 3 días.

4. **Power BI** → **retirado del alcance**, se documenta en §7.5 Futuras
   líneas.

5. **Observación por satélite** → **futura línea**. CAMS (previsión) ya
   cubre el "sustrato europeo común" para la ablación de §7.3.

6. **CI que no bloquea merges (tarea 101)** → **se deja como está**; se
   documenta como limitación en §7.4. No se activa branch protection ni se
   cambia `merge_pr()` antes del cierre.

7. **Decisión 8, resuelta 29/8 (al escribir `VIC_05`)**: se recorta §7.3 a
   la comparación baseline vs LightGBM vs GNN + explicabilidad, ya escrita
   con datos reales. Las dos ablaciones (fusión multi-señal vs fuente
   única; "solo sustrato europeo común") se descartan **para esta
   entrega** por tiempo — `ML_08` (que las produciría) no está construido
   y quedan ~2.5 semanas. Documentado como decisión explícita en `VIC_05`,
   no como omisión; revisar con el equipo si aparece margen antes del
   17/9.

## 6. Triage por deadline (~2.5 semanas) — orden acordado

Dos pistas en paralelo: **Sistema** (Filippos + tickets `FIL_*`) y
**Memoria** (Víctor + tickets `VIC_*`, arrancan desde el día 1 sin depender
de código nuevo).

| # | Ítem | Pista | Estado 28/8 |
|---|---|---|---|
| 1 | **`modelado/` — fundación (Tier 0)**: feature store, arnés de CV temporal, líneas base, MLflow, Evidently, export ONNX | Sistema | 🟡 **mayoría hecha** — `ML_02`/`ML_03`/`ML_04`/`ML_05`/`ML_06` ✅ (verificado 29/8, ver filas 4/5); `ML_01` (feature store) 🟡 con gaps reales (falta join real de meteo/previsión AEMET, festivos desde fichero real); export ONNX (`ML_07`) ⬜ |
| 2 | **`FIL_01`** + **`FIL_02`→`FIL_06`** + **`FIL_08`** — fundación de datos | Sistema | ✅ **mayoría cerrada** (PRs #150-155) — `FIL_01`/`02`/`04`/`06`/`08` ✅; `FIL_03`/`FIL_05` Ingesta→Bronze ✅ (Silver/Gold aplazado, el JSON Bronze ya es consumible); `FIL_07` ⬜ (prioridad más baja). Ver `tasks/FIL_00_README.md`. La instancia real de Neo4j tiene aforos + 203 parques + sus `PROXIMO_A`; `afluencia_lugares` ya es una tabla Gold horaria derivada de sensores |
| 3 | **`VIC_01`–`VIC_04`** — reescritura de §5–§6 a la realidad | Memoria | ✅ **hecho (29/8)** — §5, §6.1–6.4, §6.5–6.6, §6.7–6.8 reescritas directamente en el `.docx` (Kafka/Flink/Delta/Power BI/streaming fuera de la descripción del sistema construido, solo en §7.5 con motivo). Ver notas "Hecho" en `tasks/VIC_01`–`VIC_04` |
| 4 | **Tier 1** — forecasters LightGBM (AQ, congestión, afluencia) + clasificadores de episodio + SHAP | Sistema | ✅ **hecho (regresión)** — `ML_03`. Verificado 29/8, independientemente de la nota del propio ticket: 3/3 tests en verde (tras instalar `libgomp1`, ausente en esta EC2 y necesario para LightGBM), métricas reales en `modelado/evaluation/artifacts/tier1_{calidad_aire,trafico}.csv` (skill score 0.29–0.78 sobre la mejor línea base). Clasificador de episodio → `ML_08` |
| 5 | **Tier 2** — GNN espacio-temporal multi-tarea + importancia de aristas | Sistema | ✅ **hecho y verificado 29/8** — `ML_05`. `torch 2.13 cpu` instalado; STGNN entrenado end-to-end en los dos targets: `calidad_aire` (54 nodos) bate a persistencia a h3/h6 (+0.48/+0.55), `trafico` (1798 nodos) la bate en todos los horizontes (+0.39/+0.64/+0.79). 2 modelos `@champion` en MLflow. Importancia de aristas interpretable. 27 tests. Ver `doc/ML-05` |
| 6 | **`VIC_05`–`VIC_06`** — §7 usando 4–5 salidas reales de los modelos | Memoria | ✅ **hecho (29/8)** — `VIC_06`: §7.4 (4→7 limitaciones) y §7.5 (5→10 futuras líneas). `VIC_05`: Tabla 3 reconstruida con MAE/RMSE/skill real por fuente/horizonte/modelo (Tier 1 vs Tier 2 vs línea base), explicabilidad real (SHAP + importancia de aristas); ablaciones de la decisión 8 descartadas para esta entrega (documentado el motivo, no omitido) |
| 7 | **Tier 4** — tool `*_prevista` (ONNX), reentrenamiento nocturno, backtest incremental | Sistema | ⬜ |
| 8 | **`FIL_07`** (EMT multi-parada) — aditivo, la prioridad más baja | Sistema | ⬜ |

### ~~Bloqueo (28/8): recarga de Neo4j~~ Resuelto — `FIL_08` (PR #154)

`cargar_grafo.py` caía por `SessionExpired` en recargas largas contra
AuraDB Free (4 fallos el 28/8). `FIL_08` reescribió `_run_all` con `UNWIND`
por lotes + reintento/reconexión: recarga completa en **~9 min, limpia**.
Con eso se cerró `FIL_04` (203 parques con `PROXIMO_A`) y `FIL_06` parte 2.

## 7. Siguiente paso inmediato

- ~~`FIL_08`~~ — hecho.
- ~~Crear los tickets numerados de ML en `tasks/` (`modelado/`)~~ — hecho.
- ~~Resolver la decisión 8 (ablaciones de §7.3)~~ — resuelta 29/8, ver
  sección 5, punto 7.
- Los 7 tickets `VIC_*` están cerrados — la memoria ya no es el cuello de
  botella. Quedan: `ML_07`–`ML_10` (Tier 4), `modelado/` en CI (ticket
  `103`), y revisión editorial humana de todo lo reescrito.

---

## Prioridad 1 — ~~Reconciliar el drift de Terraform~~ Hecho (Sistema)

**Hecho (tarea 098)**: el plan real (recapturado, `10 to add, 55 to
change, 5 to destroy` según `doc/093` había subido a `55/65/50` por más
trabajo fusionado entre medias) se aplicó completo salvo la infraestructura
de Kafka (tarea 042, deliberadamente excluida vía `-target` sobre los 329
recursos ya en `state`, no vía `-exclude` — no soportado en esta versión de
Terraform). `terraform apply`: **50 added, 64 changed, 50 destroyed**, sin
errores. Un `terraform plan` posterior sin acotar confirma el estado
deseado: solo Kafka pendiente (`5 to add, 0 to change, 0 to destroy`).

Bloqueo real encontrado y resuelto en el camino: el usuario IAM local
(`madrono-terraform-deployer`) no tenía el permiso `codebuild:
BatchGetProjects` que sí tenía el rol de instancia EC2
(`madrono-terraform-deployerEC2`) usado por sesiones anteriores — sin él,
`terraform plan` fallaba en cascada y mostraba cifras infladas/incorrectas
en vez de un error claro. Arreglado con una política inline acotada al
ARN exacto del proyecto de CodeBuild (no la managed policy completa,
bloqueada además por la cuota de 10 políticas/usuario). Ver `doc/098` para
el detalle completo, incluida la verificación línea a línea de cada uno de
los ~170 cambios antes de aplicar nada.

## Prioridad 2 — ~~Tablas Gold rotas o inalcanzables~~ Hecho (Sistema)

| Dataset | Síntoma | Causa | Dónde está documentado |
|---|---|---|---|
| `aparcamientos` | ~~Job `SUCCEEDED`, 0 filas escritas~~ **Resuelto** | Efecto colateral no documentado de la reescritura de lectura incremental (tareas 072/075) — ya no tenía el bug. Verificado con Athena real: 601 filas/día hasta hoy | `doc/090` |
| `cartelera_cines_estrenos` | ~~Job falla (`AnalysisException`)~~ **Resuelto** | Causa real más profunda que "Silver vacío": sin escritor programado de sesiones (solo `sweep_premieres`), la puerta de calidad rechazaba el 100% de los lotes. Añadido `sweep_showtimes`/`event.tipo=="sesiones"` + schedule Terraform; de paso, arreglado un bug real (`Column 'fecha' does not exist`) presente también en `agenda_eventos` (rompiendo producción desde el 08-23) y `bluesky_menciones` | `doc/090` |
| `afluencia_lugares` | Ya no es prioridad — ver tarea 086 | Bloqueado por Google Maps, sustituido | `doc/012`, `doc/083` |
| `aforos_peatones_bicicletas` | ~~Athena devuelve 0 filas pese a que el Parquet real existe en S3~~ **Resuelto (tarea 098)** | `projection.date.range`/`projection.fecha.range` ampliado de `"2026-08-01,NOW+1DAY"` a `"2024-01-01,NOW+1DAY"`, aplicado de verdad. Verificado con Athena real tras el `apply`, sin ningún `MSCK REPAIR`: **1971 filas** en Silver y en Gold (antes 0) | `doc/087`, `doc/090`, `doc/098` |

Ya no queda ninguna tabla Gold rota ni bloqueada. `aforos_peatones_
bicicletas` sigue sin ser señal *en vivo* (la fuente municipal está
descontinuada desde 2024-06-30) — el desbloqueo da acceso real al
histórico 2019-2024 para análisis/ML; `afluencia_estimada` (tarea 089) no
dependía de ella. Pendiente, si se decide usarlo: relanzar
`grafo/cargar_grafo.py` para que los nodos de aforos entren también al
grafo (tarea 087) — fuera del alcance de la 098, que solo restauraba el
acceso vía Athena.

## Prioridad 3 — ~~Implementar la tarea 086 (afluencia por grafo)~~ Hecho, rediseñada (Sistema)

**Hecho (tarea 089), con un diseño distinto al original de esta prioridad**:
la especificación original de la tarea 086 usaba `aforos_peatones_
bicicletas` como señal primaria (proxy real de peatones) — descartada tras
la tarea 087, que confirmó que esa fuente municipal está descontinuada
desde 2024-06-30 (ver `doc/087`). `afluencia_estimada` (tarea 089, ya real
y verificada en vivo) combina en su lugar tráfico + ruido + BiciMAD +
calidad del aire vía el grafo Neo4j (mismo patrón que `trafico_cercano`,
tarea 081) — ver `asistente/README.md`. No depende de la Prioridad 2.

## Prioridad 4 — ~~Resto de tools del asistente~~ Completada (Sistema)

`asistente/README.md` ya documenta el patrón (task 079: una tool de
extremo a extremo por tarea, no varias a la vez). **Las 6 `tools`
originales del esqueleto de la tarea 044 ya tienen lógica real** — no
queda ninguna con `NotImplementedError`:

- ~~`opciones_movilidad`~~ **Hecho (tarea 096)** — simplificación
  deliberada: sin routing real por calles (no existe ningún grafo
  transitable, `CONECTADO_CON` de la tarea 071 solo conecta paradas a lo
  largo de una línea CRTM), describe condiciones de tráfico/BiciMAD/EMT
  cerca de origen y destino por separado, `duracion_estimada_min` queda
  siempre en `None`. Verificado en vivo (`GET /opciones-movilidad`) —
  confirma también la cobertura muy limitada de EMT (fila de abajo:
  "sin datos" en ambos extremos para "Retiro"→"Sol"), ver `doc/096`
- ~~`disponibilidad_aparcamiento`~~ **Hecho (tarea 090)** — real, vía Athena
  directo (una sola tabla, sin grafo), verificado en vivo
  (`GET /disponibilidad-aparcamiento`), ver `doc/090`
- ~~`eventos_cercanos`~~ **Hecho (tarea 095)** — resuelve el lugar contra el
  grafo y filtra por distancia real contra **Silver** de `agenda_eventos`
  (Gold agrega por categoría/distrito/fecha, sin lat/lon por evento;
  `agenda_recintos_madrid` queda fuera, sin pipeline Silver/Gold propio
  todavía), verificado en vivo (`GET /eventos-cercanos`) — encontró y
  corrigió dos bugs reales (columna de partición `fecha` vs `date`, y
  deduplicación por `event_id`), ver `doc/095`
- ~~Persistir `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros
  SSM `SecureString`~~ **Ya existen** (confirmado en la tarea 095,
  `/madrono-tfm/dev/secrets/neo4j-*`) — el gap de la tarea 043 se cerró en
  algún momento entre la 081 y la 095, sin documentarlo aquí. Sigue
  pendiente repetir con ellas la verificación completa de `trafico_cercano`/
  `afluencia_estimada` contra Neo4j real (la 081 solo pudo verificar la
  mitad de Athena/Gold), ver `asistente/README.md`.

## Prioridad 5 — ~~CI mínima~~ Hecho, parcial (Sistema)

**Hecho (tarea 097)**: `.github/workflows/ci.yml`, dos jobs en cada PR/push
a `main` — `tests` (841 tests reales de `ingesta/`/`procesamiento/`/
`grafo/`/`asistente/`/`herramientas/`, ninguno necesita credenciales) y
`terraform` (`fmt -check` + `validate`, sin backend remoto —
`init -backend=false`, deliberadamente sin necesitar credenciales AWS como
secreto de este repositorio). De paso corrigió el nit de formato real que
`doc/090`/`doc/093` ya habían dejado en `lambda.tf` (bloqueaba
`fmt -check`) y 3 tests con `read_text()` sin `encoding="utf-8"` explícito
(fallaban en Windows, nunca en Linux -- por eso no se habían visto en CI
hasta ahora, que no existía).

**Sigue pendiente, fuera de esta tarea**: `terraform plan` de solo lectura
en cada PR -- necesita credenciales AWS reales como secreto del
repositorio (recomendado: rol OIDC de solo lectura, no claves estáticas),
una decisión que le corresponde a quien administra el repositorio en
GitHub, no a esta tarea.

**QA (tarea 101)**: la CI corre y suele estar en verde, pero hoy no
bloquea ningún merge real -- `main` no tiene branch protection
(`gh api .../branches/main/protection` → 404) y las tareas `force: true`
fusionan su PR (`merge_pr()`, `tasks/scripts/gh_git.py:164`) sin esperar en
absoluto a que los checks de CI terminen. `doc/101-...md` documenta las dos
recomendaciones (activar branch protection exigiendo los checks `tests` +
`terraform`, y hacer que `merge_pr()` espere a los checks antes de
fusionar) con el comando/diseño ya listos para aplicar -- pendientes de
aprobación humana explícita antes de ejecutarse, ninguno aplicado todavía.

## Prioridad 6 — Memoria (Memoria, y Ambos para §5-§7)

`PLAN.md` ya tiene el reparto exacto por sección
([tabla en PLAN.md](PLAN.md#memoria--reparto-por-sección)) — no se
duplica aquí. Dos añadidos de esta sesión:

- §5 Arquitectura: usar `PLATFORM_SCHEMA.md` como fuente adicional (ya
  verificado contra la cuenta real, no solo contra `doc/`).
- §6.8 Ética/legal: la sección "zona gris académica" de `doc/012` sigue
  siendo contenido válido — el hallazgo de la tarea 083 (Google Maps exige
  facturación incluso en el nivel gratuito) es un dato nuevo y verificado
  que refuerza, no invalida, esa discusión.
- §7.4 Limitaciones: la decisión editorial pendiente en `PLAN.md`
  (bloqueador 3) debería incorporar también el drift de Terraform y las 3
  tablas Gold rotas como limitaciones reales del sistema a fecha de
  entrega, si no se llegan a resolver todas antes del 17/9.

## Prioridad 7 — Gaps menores, sin bloquear nada (Sistema)

- ~~`transporte_publico_emt` Gold solo tiene 1 `stop_id` real distinto —
  ¿límite de la fuente o bug de captura?~~ **Investigado (28/8): ninguno de
  los dos.** `ingesta/capturas/transporte_publico_madrid.py` consulta el
  endpoint EMT de llegadas, que es de **una parada por llamada**, y tanto
  `capture_all()` como `lambda_handler()` usan un único `config.stop_id`
  (por defecto `"71"`, heredado de la muestra puntual de las tareas
  003/024). La EMT publica miles de paradas — ampliarlo es una **feature
  nueva** (enumerar `stop_id` desde `crtm_red_transporte_madrid` o un
  endpoint de paradas EMT, y recorrerlos respetando el rate-limit de
  MobilityLabs), no un arreglo. Encolar como tarea del agente solo si se
  decide que la cobertura EMT importa para el asistente antes del 17/9;
  hoy `trafico_cercano`/`opciones_movilidad` ya funcionan sin ella.
- ~~`grafo/README.md` sigue diciendo "no existe ninguna instancia Neo4j
  real"~~ **Corregido (28/8)**: `grafo/README.md` e `infra/neo4j/README.md`
  llevan una nota de estado que refleja que la instancia existe y está
  cargada (tareas 080/087/094) y que el esquema se aplicó el 26/8.
- ~~**Recargar el grafo real con los nodos de aforos (tarea 087)**~~
  **Hecho (28/8)**: se encontró y arregló un segundo bloqueador
  (`grafo/extract.py` filtraba aforos a los últimos 14 días; la fuente está
  congelada en 2024-06-30 → 0 filas siempre). Quitado el filtro solo para
  esa función. Recarga real ejecutada: **83** `:EstacionMedida {tipo:
  "aforos_peatones_bicicletas"}` en la instancia real, **38** con
  `PROXIMO_A` a un `:Lugar`. Ver `doc/094` §"Actualización 28/8".
  Enriquecimiento OSM **sigue en 0** — pendiente una captura Overpass
  completa a Bronze (trabajo mayor, `doc/083`/`doc/094`).
- Visibilidad de coste: dar de alta `ce:GetCostAndUsage` sigue pendiente
  (bloqueado antes por el clasificador de seguridad del entorno, `doc/078`)
  — revisar si merece reintentarse antes del cierre.

## Cómo usar este documento

Actualízalo según se cierre cada prioridad (tachar o mover a
`PROGRESS.md` con fecha). No repite lo que ya vive en `PLAN.md` (reparto,
bloqueadores del equipo) — se centra en **qué falta técnicamente y en qué
orden**, con el porqué de cada orden.
