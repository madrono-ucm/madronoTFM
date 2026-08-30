# VIKT-09 — Pasada final de consistencia memoria ↔ código (30/8, post FIL_11–19 + congelación)

Metodología de `VIKT_01` (29/8) repetida sobre §5/§6/§7 completos, contra el
repo tal como queda tras `FIL_11`–`FIL_19` y la congelación del pipeline.
Extracción fresca de `documents/Memoria_TFM FV.docx` vía `python-docx`
(145 párrafos + 3 tablas), contrastada contra el código real y contra los
números reproducidos en `VIKT_08`.

**Nota de proceso**: las correcciones de "redacción menor" que pide este
ticket están **especificadas exactamente (texto viejo → texto nuevo) pero
NO aplicadas** — el clasificador de modo automático de esta sesión bloqueó
la escritura directa sobre `documents/Memoria_TFM FV.docx` vía
`python-docx` (mismo tipo de restricción que ya bloqueó el acceso a los
secretos de Neo4j en `VIKT_06`/`VIKT_08`), tanto en un heredoc inline como
en un fichero de script aparte. No se ha intentado ningún rodeo. Quien
tenga permiso para editar el `.docx` en esta sesión (o lo haga desde otra)
puede aplicar los 7 cambios de la sección 1 tal cual están escritos abajo.

## 1. Discrepancias con fix ya redactado (redacción menor, listo para aplicar)

Todas verificadas: párrafo exacto localizado por índice en
`d.paragraphs[i]` (extracción fresca de hoy), cambio mínimo, un solo
`run` por párrafo (sin riesgo de romper formato al reemplazar).

| § | Párrafo (índice) | Qué decía | Qué debería decir | Por qué |
|---|---|---|---|---|
| 5.4/5.5 | 73 | "su programación periódica en producción es el último paso de despliegue pendiente" | "...ya está desplegada mediante una tarea `cron` nocturna en la instancia, verificada con ejecuciones reales" | El cron de reentrenamiento (tarea 105) está desplegado y corriendo desde hace días — `/etc/cron.d/madrono-retrain` real, `historial.csv` con filas reales de 29–30/8 |
| 6.1 | 76 | "dos de las dieciséis [...] tienen por ahora solo la ingesta a Bronze" | "tres de las dieciséis [...] y parques y jardines, tienen por ahora solo..." | `parques_jardines` está en `local.producers` (Lambda + `EventBridge Scheduler` real, `madrono-tfm-dev-parques_jardines`) desde `FIL_04` (28/8) — Bronze-only, sin Silver/Gold, mismo caso que EMT/SER |
| 6.1 | 79 | "...pendiente de despliegue, parques y jardines." | (frase eliminada — ya cubierto por el matiz de 76) | Mismo motivo — `parques_jardines` ya está desplegado, solo le falta Silver/Gold |
| 6.7 | 92 | "...con **siete** herramientas reales —calidad del aire, tráfico cercano, afluencia estimada, disponibilidad de aparcamiento, eventos cercanos, opciones de movilidad y previsión de calidad del aire—... la séptima, `calidad_aire_prevista`..." | "...con **nueve** herramientas reales [...] previsión de calidad del aire, previsión de tráfico y afluencia prevista—... `calidad_aire_prevista` y `trafico_prevista` corren sendos modelos [...]; `afluencia_prevista` deriva su previsión de `trafico_prevista`..." | `FIL_13` (`trafico_prevista`) y `FIL_14` (`afluencia_prevista`) añadieron 2 tools reales — verificado en vivo (9 tools registradas, `server.py`) en `VIKT_06` |
| 6.7 | 99 | "verificada de extremo a extremo para las **7** tools reales" | "...para las **9** tools reales" | Mismo motivo que 92 |
| 7.4 | 116 | "...todavía no está desplegada — es el último paso pendiente..." | "...ya está desplegada, verificada con ejecuciones reales en producción (incluida al menos una promoción y un rechazo reales el mismo día por la guarda de regresión)..." | Mismo motivo que 73 — evidencia real: `historial.csv` 30/8 muestra `trafico` h6 promovido (`0,746>0,734`) y `calidad_aire` h1/h3 rechazados (`skill_nuevo` negativo) el mismo día |
| 7.5 | 130 | "...una vez resuelto, habilitaría una tool `afluencia_prevista` servida igual que `calidad_aire_prevista`." | "...permitiría servir el STGNN de tráfico como previsión [...] (`afluencia_prevista` ya existe como tool real, derivada de `trafico_prevista` [...], sin depender de este export)." | `afluencia_prevista` ya existe (`FIL_14`, opción "vía derivada", **no** vía STGNN→ONNX) — la memoria la presenta como bloqueada por una limitación que en realidad ya se rodeó por otro camino |

## 2. Discrepancia grande — Tabla 3 no reproduce con el código actual (routing: `VIKT_05`, ya abierto)

**No se toca aquí** (ya hay un ticket dedicado con la investigación previa,
`VIKT_05`) pero se aporta evidencia numérica nueva y concreta que hace el
caso más urgente de lo que `VIKT_05` documentó inicialmente:

| Fuente | h | Tabla 3 (memoria, LightGBM) | Reproducido en `VIKT_08` (30/8, mismo código, panel regenerado) |
|---|---|---|---|
| Calidad del aire | 1 | skill 0,29 | skill 0,051 |
| Calidad del aire | 3 | skill 0,58 | skill 0,172 |
| Calidad del aire | 6 | skill 0,68 | skill 0,209 |
| Tráfico | 1 | skill 0,37 | skill 0,322 |
| Tráfico | 3 | skill 0,61 | skill 0,557 |
| Tráfico | 6 | skill 0,76 | skill 0,684 |

Tráfico es razonablemente cercano; **calidad del aire difiere entre 3x y
5,6x** — mucho más allá de ruido estadístico normal entre corridas. Esto es
consistente con lo que `VIKT_05` ya diagnosticó por fechas de fichero (los
paneles de `modelado/_data/` se regeneraron con las features exógenas de
`ML_01` **después** de que se generaran los `comparacion_*.csv` que
alimentan la Tabla 3 actual), pero esta pasada lo confirma con números
reales, no solo con timestamps: la Tabla 3 publicada es de un panel viejo,
y el actual (con `meteo_*`/`prev_*`/`es_festivo`) da resultados bastante
distintos para calidad del aire en concreto.

**Recomendación explícita**: dado el tamaño de la diferencia, re-ejecutar
`python -m modelado.evaluation.estudios.run_all --mlflow estudios` (barato,
paneles ya materializados) y refrescar la Tabla 3 antes de la entrega tiene
más prioridad de la que `VIKT_05` le dio inicialmente — no es solo "una
mejora sin reflejar", es que los números publicados no son los que produce
el pipeline actual.

## 3. Omisiones (ni contradicen ni confirman — no mencionado en absoluto)

No requieren corrección de una frase existente, sino una decisión de si
añadir contenido nuevo (fuera del alcance de "redacción menor" de este
ticket → recomendado para `VIKT_07`/`VIKT_10`):

- **Congelación del pipeline** (30/8, `pipeline_enabled=false`): no
  aparece en ningún sitio de §5/§6/§7. Cualquier frase que diga "en
  producción continua"/"cada hora"/"diariamente" (párrafos 76, 89, 99) es
  técnicamente cierta sobre la arquitectura pero no menciona que el
  disparo automático está apagado desde el 30/8. **Ya asignado a
  `VIKT_07`** (§7.4, lista de limitaciones consolidada) — no se duplica
  aquí.
- **Respuesta a incidentes reales** (`FIL_09` librería Glue rota, `FIL_10`
  keys estables, `FIL_11` Gold congelado por filtro a "hoy", `FIL_12`
  backfill horario): 4 incidentes reales diagnosticados con causa raíz +
  fix + verificación, ninguno mencionado en la memoria. Es una fortaleza
  real del proyecto (rigor operativo) que hoy no se cuenta en ningún sitio
  — candidato a una frase nueva en §5.4/5.5 (DevOps) o como evidencia en
  §7.4, no un simple "corregir una frase que está mal".
- **`bluesky_menciones` con autenticación** (tras 28h caído por
  rate-limit anónimo): mismo caso — no mencionado, no contradice nada.
- **`FIL_16` (alertado de salud) / `FIL_17` (secretos en runtime SSM)**:
  grep limpio de "alertado"/"SSM"/"secreto" — cero menciones. Ambos son
  trabajo real ya hecho y verificado (`VIKT_09` de hoy) que podría
  mencionarse en §5.4/5.5 como madurez operativa, o dejarse fuera si se
  prefiere no ampliar esa sección tan cerca de la entrega.

## 4. Grep de términos obsoletos

- `"congelad"` → 0 resultados en la memoria (ver §3 arriba).
- `"alertad"`, `"SSM"`, `"secreto"` → 0 resultados (ver §3).
- `"siete"`/`"7 tools"` → 2 resultados, ambos corregidos en §1 (párrafos 92, 99).
- `"pendiente de despliegue"` (parques y jardines) → corregido en §1
  (párrafo 79).
- Sin datos inventados detectados: todas las cifras que cita la memoria en
  §7 (Tabla 3, backtest, paridad ONNX) tienen un artefacto real
  correspondiente en `modelado/evaluation/artifacts/` o en el registry
  MLflow — la única discrepancia es la de §2 (número desactualizado, no
  inventado).

## 5. Hallazgo colateral (fuera del alcance de este ticket, corregido aparte)

Verificando §6.1 contra `infra/terraform/lambda.tf::local.producers` para
esta pasada, se encontró que el **Catálogo de Datos** (artifact publicado
en una sesión anterior de esta misma conversación) categorizaba
`parques_jardines`/`ser_calles` como "solo Bronze, sin Lambda continuo" —
incorrecto, ambos SÍ tienen `Lambda + EventBridge Scheduler` real
(`madrono-tfm-dev-parques_jardines`/`-ser_calles`), solo les falta
Silver/Gold. Corregido directamente en el artifact (no es parte del repo
git, no requiere ticket `FIL_*`). También encontrado: `tasks/FIL_04_deploy-parques-jardines.md`
tiene `status: pending` en el front-matter pese a que el cuerpo dice
"✅ HECHO" desde el 28/8 — mismo patrón de desfase de bookkeeping que se ha
visto repetidamente en este proyecto; corregido junto con este ticket.

## Resumen

- 7 discrepancias de redacción menor: **especificadas, no aplicadas**
  (bloqueo de permisos de esta sesión sobre el `.docx`).
- 1 discrepancia grande (Tabla 3): evidencia numérica nueva aportada a
  `VIKT_05`, ya abierto — no se toca aquí.
- 3 omisiones de contenido nuevo: recomendadas para `VIKT_07`/`VIKT_10`.
- Grep de términos obsoletos limpio salvo lo ya listado arriba.
- 1 hallazgo colateral corregido (Catálogo de Datos artifact + `FIL_04`
  status).
