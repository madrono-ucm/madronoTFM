# Plan de revisión completa del TFM — evaluación de estado, huecos y hoja de ruta

**Fecha:** 2026-08-30 · **Entrega:** 2026-09-17 (~2,5 semanas) · **Gasto AWS acumulado:** ~280 USD
**Estado del pipeline:** ⏸ **ingesta congelada** (`pipeline_enabled=false`) — el trabajo restante
es solo de ingeniería sobre los datos ya presentes.

Este documento es la evaluación transversal que pidió el usuario: qué está hecho y verificado,
qué falta para cerrar el TFM, y qué separa el build actual de un build de **ingeniería de
nivel empresarial**. La ejecución se reparte en tickets `FIL_*` (Sistema / ingeniería) y
`VIKT_*` (revisión, QA, consistencia con la memoria).

---

## 1. Estado actual — qué está construido y verificado

| Capa | Estado | Evidencia |
|---|---|---|
| **Ingesta** | ✅ 16 productores (Lambda + EventBridge Scheduler) → Bronze. Congelados el 30/8. | `ingesta/`, `doc/090`, `doc/FIL-03/04/05`, `infra/OPERACION.md` §"CONGELADA" |
| **Procesamiento** | ✅ ~48 jobs Glue Bronze→Silver→Gold con puertas de calidad Great Expectations por dataset. Athena + partition projection. | `procesamiento/`, `doc/052/064/068`, `doc/FIL-11` |
| **Grafo** | ✅ Neo4j AuraDB Free cargado (distritos, barrios, estaciones, paradas, lugares, `PROXIMO_A`/`CONECTADO_CON`). | `grafo/`, `doc/080/087/094`, `doc/FIL-08` |
| **Feature store (ML_01)** | ✅ Panel horario sin fuga temporal: lags/rolling + calendario + **meteo observada + previsión AEMET + festivos reales** + vecinos de grafo. 30 features. | `modelado/features/`, `doc/ML-01`, `exogenas.py` |
| **Modelos Tier 1** | ✅ LightGBM multi-horizonte (h1/h3/h6) para `calidad_aire` y `trafico` + SHAP. Baten a persistencia/climatología. | `modelado/models/gbt.py`, `doc/ML-03`, `artifacts/tier1_*.csv` |
| **Modelo Tier 2 (grafo)** | ✅ STGNN (GraphSAGE+GRU hecho a mano) multi-tarea + importancia de aristas. Bate a persistencia en `trafico` en todos los horizontes. | `modelado/models/stgnn.py`, `doc/ML-05` |
| **MLOps** | ✅ MLflow tracking + registry (SQLite, alias `@champion`), Evidently drift (PSI+KS), export ONNX + test de paridad, cuadernos §7, reentrenamiento nocturno + backtest incremental. | `doc/ML-04/06/07/08/10`, `modelado/export/CONTRATO.md` |
| **Asistente / MCP** | 🟡 FastAPI + servidor MCP (`mcp` 2.0.0, montado en HTTP + ejecutable en `stdio`). **7 tools con lógica real.** 1 tool sirve previsión ML (`calidad_aire_prevista`, ONNX). | `asistente/`, `doc/079/081/089/095/096`, `doc/ML-09` |
| **CI / gobernanza** | ✅ 900+ tests + `terraform fmt/validate` en cada PR. **Branch protection** (checks `tests`+`terraform` obligatorios). `merge_pr()` espera a la CI verde. | `.github/workflows/ci.yml`, `doc/097/101` |
| **IaC** | ✅ Terraform para todo (Glue, Lambda, IAM de mínimo privilegio **por dataset**, EventBridge, Athena). Kafka sin aplicar a propósito. Interruptor `pipeline_enabled`. | `infra/terraform/`, `doc/098/100`, PR #185 |
| **Respuesta a incidentes** | ✅ 4 incidentes reales de producción diagnosticados con causa raíz + fix + verificación (`FIL_09` librería compartida rota 28h, `FIL_10` keys estables, `FIL_11` Gold congelado, `FIL_12` backfill horario). | `doc/FIL-09/10/11`, `doc/107` |

**Lectura:** las capas de datos y de ML están **hechas y verificadas contra AWS real**. El
TFM ya tiene una historia técnica completa. Lo que falta es (a) cerrar la capa de asistente/MCP
que "llama al ML y entrega la salida", (b) la revisión de consistencia final memoria↔código,
y (c) — si se quiere presentar como build de nivel empresarial — un conjunto acotado de piezas
de operabilidad/robustez.

---

## 2. Piezas que faltan para **cerrar el TFM** (bloqueantes de la entrega)

Estas son necesarias para que la memoria sea consistente y la defensa sea sólida.

### 2.1 Asistente / MCP — la capa que "llama al ML y entrega la salida"

- **Solo `calidad_aire` tiene previsión servible.** ONNX exportado: `calidad_aire_h{1,3,6}` +
  `trafico_h6` (h1/h3 de tráfico **no** exportados). El STGNN **no** se puede pasar a ONNX
  (`torch.export`, ya documentado en §7.5). → falta `trafico_prevista` como tool. → `FIL_13`.
- **`afluencia_prevista` no existe** (la "capacidad estrella" de la memoria). `afluencia_estimada`
  es la señal *actual* derivada (FIL_06), no una previsión. La Gold derivada tiene ~1–2 días de
  histórico útil. → decisión + implementación en `FIL_14`.
- **El envoltorio de respuesta del MCP no es de calidad de producción.** Falta un esquema de
  respuesta consistente (valor + horizonte + **versión de modelo** + **ventana de datos usada** +
  incertidumbre/confianza + procedencia) y degradación elegante cuando falta un modelo/tabla.
  El transporte (`stdio` + HTTP) hay que verificarlo de punta a punta con un cliente MCP real.
  → `FIL_15`.

### 2.2 Revisión de consistencia memoria ↔ sistema

- El `.docx` describe un pipeline "en producción continua". **Se congeló el 30/8** — legítimo
  para la entrega, pero hay que decirlo en §7.4. → `VIKT_07`.
- Cambios post-`VIKT_*` sin reflejar: `FIL_11` (Gold de ruido/avisos arreglado), `FIL_12`
  (backfill del 29/8, ya a 24/24 h), `bluesky_menciones` (autenticación añadida tras 28h caído),
  `exogenas.py` (ya cubierto por `VIKT_05`). → `VIKT_09`.
- Reproducibilidad de `modelado/` desde un clon limpio (extiende `VIKT_04`). → `VIKT_08`.
- Lectura editorial humana completa del `.docx`. → `VIKT_10`.

### 2.3 Demostrabilidad para la defensa

- No hay un **guion de recorrido end-to-end** reproducible (muestra de productor → Bronze →
  Silver → Gold → grafo → el asistente responde una pregunta real usando una previsión ML).
  Es lo que más de-arriesga la defensa. → `VIKT_06`.

---

## 3. El delta hasta un build **de nivel empresarial**

Nada de esto es imprescindible para aprobar el TFM. Se separa en **"hacer antes del 17/9"**
(barato, sube mucho la percepción de rigor) y **"§7.5 futuras líneas"** (se documenta, no se
construye).

### 3.1 Hacer antes del 17/9 (acotado, alto retorno)

| Hueco empresarial | Por qué importa | Ticket |
|---|---|---|
| **Sin alertado de salud del pipeline.** Los incidentes `FIL_09`/`FIL_11` se encontraron por QA manual / suerte, no por una alarma. Un job de Glue puede dar `SUCCEEDED` escribiendo 0 filas indefinidamente. | Es *el* hueco de operabilidad más visible. Un chequeo de frescura de Gold + alarma de fallos de Glue (SNS→email) es medio día de trabajo. | `FIL_16` |
| **Secretos como variables de entorno en claro** en las Lambda (visibles en consola) en vez de `ssm:GetParameter` en runtime. Se vio al arreglar `bluesky`. | Higiene de seguridad básica que un revisor técnico mirará. | `FIL_17` |
| **Sin test de integración end-to-end.** `aggregate.py` es el proxy testeado de los jobs Spark, pero no hay un test que recorra productor→Gold→grafo→respuesta del asistente. | Demuestra que el sistema encaja, no solo sus piezas. | `FIL_18` |
| **README raíz pobre / sin guía "ejecútalo".** | Primera impresión del repo; reproducibilidad. | `FIL_19` |

### 3.2 §7.5 futuras líneas (documentar, no construir)

- **Servir el STGNN.** `torch.export` no lo soporta hoy; alternativas (TorchScript,
  `onnxruntime-extensions`, un micro-servicio con `torch` CPU) → línea futura.
- **Serving de modelos versionado** (endpoint, model cards, A/B) en vez de cargar ONNX en proceso.
- **Ruta caliente** (streaming, Kafka/Flink) — ya en §7.5.
- **Cuadro de mando** (el Power BI original) — ya en §7.5.
- **`ce:GetCostAndUsage`** para visibilidad de coste real (ver `FIL_21` opcional; el usuario ya
  tiene los pasos de alta).
- **EMT multi-parada** (`FIL_07`, nunca hecho) — aditivo, baja prioridad.
- **Rotación de secretos, WAF/rate-limiting en el asistente, trazas distribuidas.**

---

## 4. Objetivo final — definición de "hecho"

El TFM está terminado cuando:

1. **Memoria** entregada el 17/9, internamente consistente con el sistema construido —
   toda afirmación de §5/§6/§7 verificable contra el repo en el commit de entrega (`VIKT_09`).
2. **El sistema funciona de punta a punta y se puede demostrar** — guion de recorrido
   reproducible para la defensa (`VIKT_06`), con al menos **dos** tools del asistente sirviendo
   previsión ML real (`calidad_aire_prevista` + `trafico_prevista`).
3. **§7 (resultados) es real y reproducible** desde `modelado/` en un clon limpio (`VIKT_08`).
4. **Limitaciones (§7.4) honestas y completas** — ventana corta de datos, STGNN no servible por
   ONNX, sin alertado, EMT una parada, pipeline congelado para la entrega, etc. (`VIKT_07`).
5. **(Opcional, para "nivel empresarial")** los 4 huecos de §3.1 cerrados y presentados como
   parte de la ingeniería, no como deuda.

---

## 5. Hoja de ruta — tickets, prioridad y secuencia

Orden sugerido contra el 17/9. Las dos pistas corren en paralelo (`FIL_*` = usuario/Sistema,
`VIKT_*` = Memoria/revisión).

### Prioridad 1 — cierre funcional del asistente (semana 1)

| # | Ticket | Resumen | Depende de |
|---|---|---|---|
| `FIL_13` | `trafico_prevista` como tool MCP | Exportar `trafico_h1/h3` a ONNX (o aceptar h6), vendorizar en `asistente/modelos/`, tool + router espejo de `calidad_aire_prevista` | — |
| `FIL_15` | Endurecer el servidor MCP | Verificar `stdio`+HTTP con cliente MCP real; envoltorio de respuesta consistente (valor/horizonte/modelo/ventana/confianza/procedencia); degradación elegante | `FIL_13` |
| `FIL_14` | `afluencia_prevista` — decidir + implementar | (a) LightGBM sobre la Gold fina de FIL_06 documentando la limitación, (b) derivar de las previsiones de tráfico+aire vía grafo, o (c) limitación explícita de §7.4 | `FIL_13` |

### Prioridad 2 — nivel empresarial (semana 1–2, en paralelo)

| # | Ticket | Resumen |
|---|---|---|
| `FIL_16` | Alertado de salud del pipeline | Alarma CloudWatch de fallos de Glue + chequeo de frescura de Gold (`herramientas/salud/`) + SNS. Como el pipeline está congelado, el chequeo se valida contra el estado actual y se documenta cómo se dispararía en producción |
| `FIL_17` | Secretos en runtime, no en env en claro | Mover `BLUESKY_*`/`AEMET_API_KEY`/`EMT_*`/`CAMS_*` a `ssm:GetParameter` en el handler; acotar el permiso IAM |
| `FIL_18` | Test de integración end-to-end | Productor con fixture → `transform`+`aggregate` → grafo de test → aserción sobre una tool del asistente |
| `FIL_19` | README raíz + guía de ejecución | Qué es el sistema, diagrama de arquitectura real, cómo levantar el asistente en local, cómo reanudar el pipeline |

### Prioridad 3 — revisión y memoria (toda la ventana, pista `VIKT_*`)

| # | Ticket | Resumen | Toca `.docx` |
|---|---|---|---|
| `VIKT_06` | Recorrido end-to-end / demo de defensa | Guion reproducible: muestra → pipeline → Gold → grafo → asistente + previsión ML. `doc/` + material para screencast | No |
| `VIKT_07` | Lista consolidada de limitaciones §7.4 | Todas, autoritativa, post-congelación: ventana corta, hueco 29/8 (ya backfill), pipeline congelado 30/8, STGNN sin ONNX, sin alertado, EMT 1 parada, avisos verdes, auth de bluesky, afluencia fina | Sí |
| `VIKT_08` | Auditoría de reproducibilidad de `modelado/` | Clon limpio → cada tabla/figura de §7 regenerada; arreglar cualquier drift de deps; comandos exactos (extiende `VIKT_04`) | Sí (anexo) |
| `VIKT_09` | Pasada final memoria ↔ código | Cada afirmación de §5/§6/§7 contra el repo en el commit de entrega, incluyendo `FIL_11`–`FIL_19` y la congelación | Sí |
| `VIKT_10` | Coordinación de revisión editorial + defensa | Lectura humana completa del `.docx`; preparación de preguntas de defensa (por qué no Kafka / por qué congelado / por qué STGNN no servido) | Sí |

### Opcionales / §7.5 (solo si sobra tiempo)

- `FIL_20` — investigar una ruta de serving para el STGNN.
- `FIL_21` — alta de `ce:GetCostAndUsage` + `herramientas/costes/` contra Billing real.
- `FIL_22` — `FIL_07` EMT multi-parada.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **Ventana de datos fina** (14/8–30/8) — solo modelos de horizonte corto. | Ya es una decisión de diseño documentada (§7.4). El backtest incremental de `ML_10` es la evidencia de "el modelo mejora con más datos". No reabrir. |
| **STGNN no servible por ONNX.** | `calidad_aire_prevista` + `trafico_prevista` (LightGBM) cubren la demo de "MCP llama al ML". El STGNN se presenta como resultado de §7.2 + limitación de serving en §7.5. |
| **`.docx` binario, edición concurrente.** | Regla existente (`PLAN.md` §"Memoria"): una sola pista toca el `.docx` a la vez; avisar en el chat; `git pull` antes. |
| **Coincidir dos agentes en los mismos ficheros.** | `FIL_*` y `VIKT_*` tocan zonas distintas del repo. Los `apply` de Terraform se coordinan (lock de estado). |
| **Reanudar el pipeline para la defensa deja huecos horarios.** | `--backfill_fecha` por día (ver `infra/OPERACION.md`). O defender con datos congelados y explicarlo. |

---

## 7. Números libres

- Numerados (cola del demonio): próximo **108**.
- `FIL_*`: próximo **13**.
- `VIKT_*`: próximo **06**.
