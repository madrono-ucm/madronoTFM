---
kind: vic-index
owner: Víctor (Pista Memoria)
created_at: "2026-08-28"
---

# `VIC_*` tickets — Memoria (thesis document) track

`documents/Memoria_TFM FV.docx` is dated June 2026 and describes an
architecture that in several places was **not built** (Kafka/Flink/Delta
Lake, MLflow, Power BI). Decision (28/8, `NEXT_STEPS.md` §5.2): **rewrite to
the real system as a justified cost-0 design choice**, and move the
unbuilt pieces to §7.5 *Futuras líneas*.

These `VIC_*` tickets are **outside the autonomous `madrono-agent` queue**
(the daemon only picks up `^\d+-[a-z0-9-]+\.md$`). Víctor works them in
parallel with the Sistema track — they don't depend on new code, and each
one points at the **living technical sources** so the memoria tracks the
real state of the repo as it evolves.

## How to use each ticket

Every ticket lists: the section(s) to write, the **fuente técnica** to read
first (`doc/NNN-*.md`, `PLATFORM_SCHEMA.md`, the module READMEs,
`NEXT_STEPS.md`), the key claims that must change vs the June draft, and
what stays. Coordinate edits on the `.docx` per `PLAN.md` (turn-taking /
Word Online) — it does not merge in git.

## Tickets

| Ticket | Sección(es) | Depende de | Estado |
|---|---|---|---|
| `VIC_01` | §5 Arquitectura (rewrite to real stack) | — | ✅ done 29/8 (Claude) |
| `VIC_02` | §6.1–6.4 Fuentes, preparación, flujos | — | ✅ done 29/8 (Claude) |
| `VIC_03` | §6.5 Orquestación · §6.6 Almacenamiento y consulta | — | ✅ done 29/8 (Claude) |
| `VIC_04` | §6.7 Explotación · §6.8 Ética/legal | FIL_06 landing helps §6.7/§6.8 | ✅ done 29/8 (Claude) — FIL_06 already landed |
| `VIC_05` | §7.1–7.3 Resultados, métricas, comparativas | ML Tier 1 + Tier 2 outputs | ✅ done 29/8 (Claude) — Tabla 3 rebuilt from scratch (real MAE/RMSE/skill by source/horizon/model), explicabilidad (SHAP + importancia de aristas), ablations from "decisión 8" explicitly descoped for this delivery (documented why, not silently dropped) |
| `VIC_06` | §7.4 Limitaciones · §7.5 Futuras líneas | — (can draft now, refine later) | ✅ done 29/8 (Claude) |
| `VIC_07` | §1 Resumen · §2 Palabras clave · §3–4 Introducción/Metodología (consistency pass) | after VIC_01–06 | ✅ done 29/8 (Claude) — no remaining false claim anywhere in the body (verified with a grep for Kafka/Avro/KSQL/Flink/streaming across the whole doc) |

`VIC_01`–`VIC_04` and `VIC_06` were written directly into the `.docx` with
`python-docx` (preserves paragraph styles/list numbering) rather than via
Word Online turn-taking — coordinate before editing further so this doesn't
collide with in-progress manual edits.

## `VIC_08`–`VIC_33` — technical evaluation rounds (not memoria writing)

Seven rounds of technical QA/eval tickets (`doc/VIC-08-...` through
`doc/VIC-33-...`) covering `ingesta/`, `procesamiento/`, `grafo/`,
`asistente/`, `modelado/`, `infra/terraform/`, CI/daemon/costes, security
(bandit/pip-audit/checkov/detect-secrets), lint (ruff), types (mypy), test
coverage, and independent verification of `FIL_16/17`'s AWS apply and
`FIL_55`'s browser-real map fix. **All 26 done** (see each `tasks/VIC_NN_*.md`
and its paired `doc/VIC-NN-*.md` report) — not itemized here individually
since they're technical evals, not memoria sections; `VIC_15`/`VIC_20`
already reconciled their findings into the `.docx`.

## `VIC_34`–`VIC_43` — QA + memoria pass after the 2026-09-09/10 burst (`FIL_64`–`83`)

A fast burst of engineering landed between the `VIKT_*` close-out and
2026-09-10 — the graph densified (`FIL_65`/`66`/`67`), tool count went
14→19 (`FIL_46`, `FIL_67` `consulta_grafo`, `FIL_79`–`83`), and new
analytics shipped (`FIL_52`/`64` centrality+resilience, `FIL_81`
centrality artifact). These 10 tickets QA'd all of it and closed the gap
in the memoria.

| Ticket | Qué | Toca `.docx` | Estado |
|---|---|---|---|
| `VIC_34` | Verificación agregada de la instancia Neo4j real tras `FIL_65`/`66`/`67` (conteos, huérfanos, atributos, schema) | No | ✅ **done 10/9 (Claude)** — limpio, 0 bugs; snapshot offline 27 nodos por detrás anotado (housekeeping, sin ticket) |
| `VIC_35` | QA de `consulta_grafo` (15ª tool, `FIL_67`) — solo lectura, contrato de degradación, guard anti-escritura, compat de `contexto_urbano` | No (código) | ✅ **done 10/9 (Claude)** — endureció `run_neo4j_query` con `access_mode="READ"`; abrió `FIL_89` (ventana deslizante de `grafo/extract.py` expirará ~13-14/9, antes de la entrega) |
| `VIC_36` | QA de la analítica de resiliencia (`FIL_64`): puntos de articulación, puentes, k-core, curva de robustez | Sí (vía `VIC_38`) | ✅ **done 10/9 (Claude)** — abrió `FIL_86` (el recálculo por lotes subestima el daño ~0,77 en un subgrafo de contraste); texto de memoria matizado ya incorporado por `VIC_38` |
| `VIC_37` | Consistencia documental tras 14→15→19 tools (recuento, endpoints, `grafo/consulta.py`) | No | ✅ **done 10/9 (Claude)** — `asistente/README.md` seguía en "7 tools"; corregido en README raíz, `asistente/README.md`, `grafo/README.md`, `infra/OPERACION.md`, `_INSTRUCCIONES` |
| `VIC_38` | Integrar los hallazgos de grafo (`FIL_52/64/65/66/67`) en §6 y §7 de la memoria | **Sí** | ✅ **done 10/9 (Claude)** — ver el propio `tasks/VIC_38_memoria-grafo-hallazgos.md` para el detalle completo; también rehizo el contenido de `VIKT_12` que se había perdido (ver nota abajo) |
| `VIC_39` | QA de `calidad_aire_episodio` (16ª tool, `FIL_79`) | No | ✅ **done 10/9 (Claude)** — abrió `FIL_87` (umbrales OMS/UE duplicados en 4 ficheros, sin módulo único) |
| `VIC_40` | QA de `calidad_aire_cams` (17ª tool, `FIL_80`) + contraste en `calidad_aire_prevista` | No | ✅ **done 10/9 (Claude)** — sin bug nuevo; arregló una brecha de aislamiento de tests que dejaba el contraste CAMS sin cobertura real |
| `VIC_41` | QA de `grafo_centralidad` (`FIL_81`): PageRank/Louvain, artefacto, explorador | No | ✅ **done 10/9 (Claude)** — abrió `FIL_85` (betweenness recalculado dos veces con la misma entrada) |
| `VIC_42` | QA de `meteo_cercana`+`avisos_meteo` (18ª/19ª tools, `FIL_82`) | No | ✅ **done 10/9 (Claude)** — abrió `FIL_88` (`meteo_cercana` no degrada fiabilidad por frescura, a diferencia de sus hermanas) |
| `VIC_43` | QA de la caché TTL + vistas Athena (`FIL_83`) | No | ✅ **done 10/9 (Claude)** — sin bug de producción; arregló contaminación de caché entre tests (17 tests flaky con `ASSISTANT_CACHE_TTL=900`) |
| `VIC_44` | QA del anclaje temporal del asistente (`FIL_84`, `ASSISTANT_ANCHOR_DATE`) | No | ⬜ en curso (10/9, Claude) |

**Nota sobre `VIKT_12`**: una sesión anterior había preparado y comiteado
localmente el contenido de `VIKT_12` (14 tools, app web, mapa animado,
secretos/alertado) pero nunca llegó a hacer `git push` — un
`git reset --hard origin/main` externo se llevó ese commit por delante
antes de que se subiera. `VIC_38` lo detectó al releer el `.docx` de cero
(seguía en "siete herramientas") y rehizo todo ese contenido en la misma
pasada, ya con las cifras reales de hoy (19 tools, no 14). Lección para
quien edite el `.docx` en el futuro: **hacer `git push` inmediatamente
después de cada commit que lo toque**, no acumular trabajo local.

Nuevos tickets `FIL_*` abiertos por esta ronda: `FIL_85`–`89` — **los 5
ya están arreglados (10/9, Claude, mismo día que se abrieron)**:

| Ticket | Arreglo | Verificado con |
|---|---|---|
| `FIL_85` | `centralidad_transporte`/`curva_robustez` comparten un `bet_inicial` en vez de calcular el mismo betweenness dos veces | test con spy (una llamada menos, mismo resultado) |
| `FIL_86` | `curva_robustez` re-etiqueta el ataque dirigido como aproximado en el artefacto, la figura y la memoria (vía 2 del ticket, sin recálculo exacto — inviable a esta escala, ~2h) | test que confirma la nota nueva |
| `FIL_87` | `asistente/umbrales.py` — fuente única de umbrales OMS/UE, ya no duplicados en 4 ficheros | import + lectura de valores tras el cambio |
| `FIL_88` | `meteo_cercana` gana `fecha` y fiabilidad `BAJA`/`MEDIA` según se dé, igual que `avisos_meteo` | tests de tool + router (`TestClient`) |
| `FIL_89` | `grafo/extract.py` ya no depende de `current_date` real — quitado el filtro de ventana en las 7 consultas afectadas | **recarga real del grafo** (14,4 min, AuraDB real) + memoria corregida con las cifras post-recarga (9812 nodos, 76156 relaciones, subárea 4439/4705) |

`FIL_89` era el único con fecha límite real (se habría vaciado en
silencio entre el 13 y el 14/9, días antes de la entrega) — ya no es un
riesgo.

## Cross-cutting: claims in the June draft that must change

- "Apache Kafka / Kafka Connect / Avro" → EventBridge Scheduler + Lambda;
  Kafka → §7.5.
- "Flink/KSQL ruta caliente / streaming en ventana" → **no hay ruta
  caliente**; el estado "instantáneo" es la última fila Gold horaria.
- "tablas Delta / Delta Lake" → Parquet + catálogo Glue + Athena Partition
  Projection.
- "MLflow / Evidently / ONNX" → sí se usan, pero descríbelos sobre el
  pipeline real de `modelado/` (no como capa genérica). Ver ML tickets.
- "cuadro de mando en Power BI" → retirado, §7.5.
- "observación por satélite" (enriquecimiento europeo) → §7.5; CAMS
  (previsión) es el sustrato europeo real usado.
- Afluencia de lugares vía `populartimes`/Google → **señal derivada** de
  sensores vía el grafo (tarea 089 + FIL_06); la discusión de "zona gris"
  de §6.8 pasa a ser una *futura línea* (proveedor comercial), no una
  dependencia activa.
