---
kind: fil-index
owner: Filippos (interactive, NOT the autonomous queue)
created_at: "2026-08-28"
---

# `FIL_*` tickets — interactive data-foundation work

These tickets are **outside the autonomous `madrono-agent` queue**. The daemon
only picks up files matching `^\d+-[a-z0-9-]+\.md$` (see
`tasks/scripts/tasks_store.py:21`), so `FIL_*` files are ignored by it and are
worked interactively by Filippos, in any order the dependencies allow, without
waiting for the numbered queue.

## Why this set exists

Session of 2026-08-28: health-check of every integrated Madrid source + a
codebase/doc scan for planned-but-missing datapoints, done because the ML
phase of the TFM (memoria objective: *"entrenar modelos predictivos de
afluencia, congestión y calidad del aire"*) needs a solid, complete data
foundation first. Findings and the full decision-making picture are in
`NEXT_STEPS.md`, sección "Estado a 28/8".

## Tickets — estado a 2026-08-28

| Ticket | Qué | Estado |
|---|---|---|
| `FIL_01` | Fix `aemet_prevision` silver→gold (fallo en prod) | ✅ **HECHO** — IAM aplicado, job → SUCCEEDED, Gold fresco (PR #151, `doc/FIL-01`) |
| `FIL_02` | `lambda_handler` + BronzeWriter en los 3 módulos de la tarea 090 | ✅ **HECHO** (PR #150) |
| `FIL_03` | Desplegar `emt_incidencias` | 🟡 **Ingesta hecha** — Lambda + schedule 30 min → Bronze real (~110 incidencias). Silver/Gold aplazado (PR #151, `doc/FIL-03-05`) |
| `FIL_04` | Desplegar `parques_jardines` + parques `:Lugar` en el grafo | ✅ **HECHO** — Lambda + schedule → Bronze (203 parques); tras `FIL_08` la recarga completa: **203 `:Lugar {tipo:"parque"}`, 199 con `PROXIMO_A` a un sensor** (antes 0) (PR #151, `doc/FIL-08`) |
| `FIL_05` | Desplegar `ser_calles` | 🟡 **Ingesta hecha** — Lambda + schedule semanal (512 MB) → Bronze (34.486 tramos). Silver/Gold + valoración `disponibilidad_aparcamiento` aplazados (PR #151) |
| `FIL_06` | `afluencia_lugares`: retirar Google Maps, señal derivada como Gold | ✅ **HECHO** — parte 1 (PR #152): Google Popular Times retirado. Parte 2 (aplicada + verificada): job horario `glue_estimada.py` (Neo4j + 4 Gold de sensores → `nivel_estimado` por `:Lugar`), trigger `SCHEDULED cron(20 * * * ? *)`; Athena 534 bajo / 7 medio / 45 sin_datos sobre 586 lugares. `doc/FIL-06` |
| `FIL_07` | `transporte_publico_emt`: capturar más de una parada | ⬜ **Sin empezar** (prioridad más baja) |
| `FIL_08` | `cargar_grafo.py` resiliente a cortes de AuraDB Free (`UNWIND` + reintento) | ✅ **HECHO** — `_run_all` por lotes `UNWIND` + reintento/reconexión; recarga real limpia en ~9 min (antes: 4 fallos / 51 min). +4 tests. Cierra `FIL_04` (PR pendiente, `doc/FIL-08`) |
| `FIL_09` | **URGENTE** — 37/48 jobs de Glue en `LAUNCH ERROR`, librería compartida `procesamiento.zip` inexistente en S3 (>28h roto) | ✅ **HECHO 29/8** — recuperación a mano (27 cadenas `SUCCEEDED`, Gold fresco en Athena) + key **estable** `glue-libs/procesamiento.zip` (PR #175) + `terraform apply` revisado y aprobado (`2 add/56 change/2 destroy`, Kafka excluido). 48/48 jobs en la key estable, objeto único en S3. Ver `doc/FIL-09-...md` § "Resultado de la ejecución" |
| `FIL_10` | Aplicar la key estable de los 48 `glue_script_*` (código de la tarea 107, no urgente) | ✅ **HECHO 29/8** — `terraform apply` aprobado por el usuario, plan fresco `48 add/48 change/48 destroy` (Kafka excluido, sin destrucciones sueltas). 48/48 `script_location` con key estable sin hash, `trafico_bronze_to_silver` → `SUCCEEDED`. `doc/107` § "Resultado de la ejecución". Cierra los dos follow-ups de `FIL_09` |
| `FIL_11` | `ruido` y `aemet_avisos` con Gold estancado pese a jobs `SUCCEEDED` a diario | ✅ **HECHO 30/8** — causa raíz: `silver_to_gold` filtraba la salida a `date == today()` (`ruido`, fuente con retraso) / leía solo `Silver/aemet_avisos/fecha=hoy` (avisos con `effective_from` futuro). Fix: `mode("overwrite")` + `partitionOverwriteMode=dynamic` + `s3:DeleteObject` (PRs #180/#181). Verificado: `ruido` Gold avanza a 26/8, `aemet_avisos` de-duplicado. `doc/FIL-11-...md` |
| `FIL_12` | `FIL_09` verificó solo frescura por fecha — 6 datasets con ~20 h perdidas el 29/8 | ✅ **HECHO 30/8 — backfill** — nuevo modo `--backfill_fecha` en los 10 jobs de los 5 datasets horarios (PR #183) + `s3:DeleteObject` IAM. Ejecutado para 29/8: 10/10 `SUCCEEDED`, los 5 datasets a **24/24 h**, 0 duplicados (Athena). `transporte_publico_emt` 20/24 (Bronze incompleto). `doc/FIL-09` §"Completitud por hora"; runbook en `infra/OPERACION.md` |
| `FIL_13` | `trafico_prevista` como tool MCP | ✅ **HECHO 30/8** — ONNX `trafico_h{1,3,6}` exportados+vendorizados, `prevision.py` a `target`, tool + `GET /trafico-prevista`, registrada (8 tools). Verificado en vivo. `doc/FIL-13-...md` |
| `FIL_14` | `afluencia_prevista`: decidir vía (modelo propio / derivada de tráfico+aire vía grafo / limitación §7.4) e implementar | ✅ **HECHO 30/8** — vía (b): señal **derivada** (`trafico_prevista` + persistencia ruido/BiciMAD, fusión de `afluencia_estimada`), sin modelo propio (Gold insuficiente + pipeline congelado). Tool + `GET /afluencia-prevista`, registrada (9 tools), `AfluenciaPrevista(RespuestaPrevision)`. `doc/FIL-14-...md` |
| `FIL_15` | Endurecer el servidor MCP: verificar transporte `stdio`+HTTP con cliente real, envoltorio de respuesta consistente (valor/horizonte/modelo/ventana/confianza), degradación elegante | ✅ **HECHO 30/8** — `RespuestaPrevision` base (herencia en `CalidadAirePrevista`/`TraficoPrevista`) con `disponible`/`momento_objetivo`/`motivo`/`generado_en`; `try/except` en Athena/Neo4j con `motivo` legible; `test_mcp_transport.py` (5, incl. `stdio` subproceso real) + `test_mcp_hardening.py` (11); README con `mcpServers`. `doc/FIL-15-...md` |
| `FIL_16` | Observabilidad: alarma CloudWatch de fallos de Glue + chequeo de frescura de Gold (`herramientas/salud/`) + SNS | ✅ **HECHO 30/8** — `herramientas/salud/frescura_gold.py` (+11 tests, verificado en vivo contra Athena) mira el dato no el job (caza el fallo tipo `FIL_11`). `infra/terraform/observabilidad.tf` (EventBridge Glue-fail → SNS → email) **diseñado, sin apply** (pipeline congelado + email needs manual confirm). `doc/FIL-16-...md` |
| `FIL_17` | Secretos en runtime (`ssm:GetParameter` en el handler) en vez de env en claro en las Lambda | ✅ **HECHO 30/8** (código) — `ingesta/capturas/secretos.py` (`get_secret`, cacheado, fallback a env); `lambda.tf` inyecta `*_SSM_PATH` no el valor; IAM `ssm:GetParameter` acotado a los 6 ARNs; 4 productores adaptados; +6 tests. `terraform apply -target` pendiente (pipeline congelado). `doc/FIL-17-...md` |
| `FIL_18` | Test de integración end-to-end: productor→`transform`+`aggregate`→grafo test→aserción sobre una tool del asistente | ✅ **HECHO 30/8** — `tests/integracion/test_e2e_bronze_a_asistente.py` (6 casos): Bronze inline → transform → aggregate → dobles Athena/Neo4j → `calidad_aire`/`calidad_aire_prevista`/`trafico_cercano`. Puerta de calidad + guardia de eslabón roto. `tests/` añadido a CI. `doc/FIL-18-...md` |
| `FIL_19` | README raíz + guía "ejecuta el asistente en local" + diagrama de arquitectura real (Mermaid) | ✅ **HECHO 30/8** — `README.md` raíz: qué es, diagrama Mermaid (lo construido + lo §7.5 marcado), estado (pipeline congelado), guía de ejecución local + `mcpServers`, layout del repo. Enlaza `infra/OPERACION.md`. |
| `FIL_20` | Serving del STGNN (opcional / §7.5) | ✅ **HECHO 30/8** — el STGNN **SÍ** se exporta a ONNX vía `torch.onnx.export(dynamo=True)`, paridad `max|Δ|~6e-8` incl. nº de nodos dinámico. `exportar_stgnn` reescrita + `--stgnn` CLI + `paridad_stgnn` + tests. **No** se sirve como tool (contrato de entrada pesado; LightGBM ya cubre la demo). La limitación §7.5 "STGNN no servible por ONNX" **ya no aplica**. `doc/FIL-20-...md` |
| `FIL_21`–`FIL_22` | Opcionales / §7.5: `ce:GetCostAndUsage` + Billing real · EMT multi-parada (`FIL_07`) | ⬜ sólo si sobra tiempo |
| `FIL_23` | `modelado/requirements.txt`: `torch>=2.2,<3` sin índice CPU resuelve al build CUDA (~4.5 GB, roto sin GPU) — hallazgo de `VIKT_08` | ✅ **HECHO 30/8** — `--extra-index-url .../whl/cpu` en `requirements.txt` (pip prefiere el wheel `+cpu`); `modelado/README.md` con arranque en dos pasos. `doc/FIL-23-...md` |
| `FIL_25` | README raíz dice "25 productores" — sólo 16 son Lambda continuos, 7 batch puntual, 1 retirado — hallazgo de `VIKT`/QA de `FIL_19` | ✅ **HECHO 30/8** — `README.md` raíz: diagrama Mermaid con caja aparte para las 7 cargas batch de referencia; fila de layout con "16 continuos + 7 batch + 1 retirado" verificable contra `lambda.tf::local.producers`. |
| `FIL_24` | `opciones_movilidad`/`eventos_cercanos` sin `output_schema` MCP (`list[Model]`) — hallazgo de `VIKT_06` | ✅ **HECHO 30/8** — contenedores `OpcionesMovilidad`/`EventosCercanos`; las 9 tools con `output_schema` (test real). `doc/FIL-24-...md` |
| `FIL_26` | Servir el STGNN (`ML_05`) como tool del MCP | ✅ **HECHO 30/8** — `calidad_aire_prevista_grafo` (10.ª tool): STGNN vía ONNX sin torch (`--meta` JSON: features/scalers/grafo/importancia de aristas), `asistente/prevision_grafo.py`, `CalidadAirePrevistaGrafo` con **`vecinos_influyentes`**. Verificado en vivo (Retiro↔Carmen O3, arista más influyente). Honesto: pierde a LightGBM a 1 h, `fiabilidad` BAJA. `doc/FIL-26-...md` |
| `FIL_31` | Servir el STGNN de **tráfico** como tool del MCP (gemela de `FIL_26`) | ✅ **HECHO 30/8** — `trafico_prevista_grafo` (11.ª tool): STGNN de tráfico (1.798 `point_id`, grafo `coords-knn8`) exportado+vendorizado, `prevision_grafo.py` parametrizado por `target` ∈ {calidad_aire, trafico}, `TraficoPrevistaGrafo` con `vecinos_influyentes`, router + `server.py` a 11 tools. Tolerancia de paridad ONNX re-expresada (mean/p99/max, criterio LightGBM) por la no-asociatividad de `float32` en el scatter-add del grafo grande. 135 tests. Honesto: pierde a LightGBM en métricas puntuales, `fiabilidad` BAJA. Habilita `FIL_32`–`FIL_37`. `doc/FIL-31-...md` |
| `FIL_32`–`FIL_36` | **Mapa animado del grafo de Madrid** (elemento "wow" del TFM) — export del grafo canónico, `prevision_animada.parquet`, HTML animado (pydeck), capas ricas + hosting en Pages, el grafo como eje de la memoria | ⬜ **En marcha** — plan, fechas objetivo, **auditoría de 10 gaps reales** (G1 partition projection deslizante → exportar Gold YA; G2 ruido sólo diario; G3 sin variedad meteo; G8 Pages sin habilitar…) y el fork Vía A/B en `viz/PROGRESO_MAPA.md`. Todo offline (cero AWS nuevo). |
| `FIL_37` | `ruta_saludable` — recomendador ambiental sobre el grafo (12.ª tool) + evaluación Pareto + caso ciclista | ⏸ **Condicional** — sólo si `FIL_31` mergea limpia y el núcleo del mapa (`FIL_34`) funciona hacia el ~día 8. Si no, queda como trabajo futuro; el spine "map-only" es el entregable seguro. |
| `FIL_38` | Backtest offline más largo (30 meses) con MTD + meteo histórica de la Comunidad | ⬜ **Opcional** — datasets descargables en local, cero AWS. No toca los ONNX vendorizados (results-only). |

### Seguimiento surgido en la ejecución

- **Recarga de Neo4j poco fiable**: `cargar_grafo.py` cae por
  `neo4j.exceptions.SessionExpired` en recargas largas contra AuraDB Free
  (falló 3 veces el 28/8). Bloquea el cierre de `FIL_04` y la parte 2 de
  `FIL_06`. Sugerido: `FIL_08` — hacer `cargar_grafo.py` resiliente (`UNWIND`
  para agrupar los `MERGE`, reconexión/reintento por lote).
- **Silver/Gold de `emt_incidencias` / `ser_calles`**: bloque `glue.tf` +
  `aggregate.py` + `ge_suite.py` + tabla Athena. Solo si la fase de ML lo
  necesita agregado; el JSON de Bronze ya es consumible.

## Deployment note

`FIL_03`–`FIL_06` include real `terraform apply` / Lambda / Glue changes.
Same guardrail as task 098: run `terraform plan`, review every change, apply,
verify data lands in Bronze→Silver→Gold and is queryable in Athena. AWS creds:
`AWS_PROFILE=madrono` (`eu-west-1`), user `madrono-terraform-deployer`.
