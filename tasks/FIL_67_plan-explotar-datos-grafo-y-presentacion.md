---
kind: fil
title: "Plan maestro: explotar todos los datos vía el grafo, consultar Neo4j directamente y reforzar la capa de presentación"
owner: Filippos (interactive)
status: in_progress
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_52, FIL_53, FIL_54, FIL_64, FIL_65, FIL_66]
milestone: "M7"
target: "2026-09-16"
---

## Punto de partida (2026-09-09)

| Activo | Estado |
|---|---|
| **Grafo Neo4j** (AuraDB `5c111cec`) | 9.806 nodos / 5 labels / 4 relaciones. Ya incluye meteo (25), recintos de eventos (145) y atributos estáticos de Gold (`contaminantes`, `magnitudes`, `altitud_m`, `subarea`, `modos`, `anclajes_totales`, `plazas_totales`). **APOC 2026.08 completo in-DBMS** (`apoc.algo.dijkstra` verificado en vivo) + **Aura Graph Analytics** (GDS por sesión). |
| **15 tablas Gold** | tráfico, aire (11 contaminantes), ruido, meteo, bicimad, aparcamiento, eventos, cines, social, afluencia derivada + 3 de previsión (CAMS ciudad, AEMET municipio, avisos AEMET). Pipeline congelado desde ~2026-08-30. |
| **ML** | 4 forecasters LightGBM ONNX + 2 STGNN (tráfico, aire) con importancia de aristas. |
| **Asistente** | 14 herramientas MCP; **solo 6 constructores Cypher fijos** en `asistente/neo4j_client.py` (matching `toLower CONTAINS`). |
| **Mapa** (`viz/mapa`) | se construye desde **JSON estático**, de **otro grafo** — el `coords-knn8` del STGNN, no Neo4j. Hay dos grafos en el proyecto. |
| **Web** | `web/index.html` landing + chat → `/chat` del asistente (Groq) → herramientas MCP. |

**Hueco principal:** el grafo real apenas se expone. El mapa lo ignora; el
asistente lo toca con 6 consultas预escritas.

**Modelo mental (para la memoria):** el grafo responde *"dónde y qué hay
cerca"*; Gold/Athena responde *"qué valor, en el tiempo"*; el ML responde
*"qué valor tendrá"*. Toda pregunta se descompone: resolver lugar →
traversal del grafo para hallar entidades/sensores relevantes → Athena para
valores recientes → ML para la previsión → componer respuesta.

---

## Parte 1 — Explotar todos los puntos de datos

| # | Acción | Usa | Esfuerzo | Ticket |
|---|---|---|---|---|
| 1 | **Consultas de aire por contaminante** — "la estación más cercana que mide de hecho O₃/PM2.5". Cablear `contaminantes` (FIL_66) en `neo4j_client.py` + herramienta `calidad_aire`. | aire Gold + grafo | S | FIL_67a |
| 2 | **Movilidad con capacidad** — `anclajes_totales` (bicimad), `plazas_totales` (aparcamiento) en `opciones_movilidad` / `disponibilidad_aparcamiento` (la ocupación % necesita la capacidad). | bicimad/aparc. Gold + grafo | S | FIL_67b |
| 3 | **Meteo como vecino de primera clase** — meteo ya está en el grafo; alimentar `meteo_*` en `contexto_urbano` y que el join exógeno del STGNN sea graph-native. | meteo Gold + grafo | S | FIL_67c |
| 4 | **Herramienta `prevision_ciudad`** — previsión CAMS de aire de ciudad + previsión AEMET por municipio no tienen sitio hoy. Una herramienta, sin grafo, cierra las tablas de previsión. | CAMS + AEMET Gold | S | FIL_67d |
| 5 | **Nodos `:Linea` + `PARA_EN`** — "líneas entre A y B", "qué líneas paran en X", "menos transbordos". El dato ya está en `CONECTADO_CON.linea`. | grafo | M | FIL_67e |
| 6 | **Recintos en el grafo para consulta directa + mapa.** ~~Reescribir `eventos_cercanos`~~ — revisado: esa tool ya resuelve el lugar vía el grafo (`resolver_lugar_query`) y solo el filtro final de distancia es Python; reescribirla a `PROXIMO_A → :Lugar{recinto}` **descartaría** eventos en recintos sin nodo (calles, sitios puntuales) con poco valor a cambio. El valor de los 145 `:Lugar{recinto}` es que ya son consultables por `grafo/consulta.py` / constructores nuevos y pintables en el mapa (Parte 3 #1). Bajar prioridad. | eventos + grafo | S | FIL_67f |
| 7 | **Agregados por `subarea`** — "tráfico en mi zona" sin geo-math; también la unidad de cluster natural del STGNN. | tráfico Gold + grafo | M | FIL_67g |
| 8 | **`:ZonaAviso` (3) → Distrito** — avisos meteo atravesables. Valor bajo, barato; solo si el demo quiere alertas. | aemet_avisos | S | FIL_67h |

**No merece la pena:** `bluesky` (sin geo); reingesta de `aforos` (fuente
muerta 2024-06-30); `transporte_publico_emt` multi-parada (eso es FIL_07,
funcionalidad de asistente, no dato de grafo).

---

## Parte 2 — Consultar Neo4j directamente

### A. Para dev (hoy, ~1 h) — FIL_67i

- **Arreglar el `NEO4J_DATABASE` por defecto**: `"neo4j"` → `None` (usa la
  home database del DBMS, que en Aura ES la real) en
  `asistente/neo4j_client.py`, `grafo/cargar_grafo.py`,
  `grafo/cypher.py::Neo4jLoader`. Hoy falla con `DatabaseNotFound` si no se
  pasa el nombre explícito.
- **`grafo/consulta.py`** — CLI de solo lectura (~40 líneas): lee creds de
  SSM, `session(default_access_mode=READ)`, imprime filas.
  `python -m grafo.consulta "MATCH (e:EstacionMedida) RETURN e.tipo, count(*)"`.
- Alternativa interactiva: consola de Aura / Neo4j Browser / Bloom con las
  creds de SSM.

### B. Para el asistente — FIL_67j (elegir una vía)

1. **Librería de consultas parametrizadas (recomendada, bajo riesgo).**
   `neo4j_client.py` pasa de 6 a ~20 plantillas nombradas, cada una
   `def …_query(**params) -> (cypher, params)`: "sensores de tipo T cerca
   del lugar P", "ruta A→B perfil P" (vía `apoc.algo.dijkstra`), "líneas que
   paran en S", "distritos ordenados por <señal> la última semana",
   "vecindario del grafo de P a profundidad D". El LLM elige plantilla +
   rellena params — mismo perfil de riesgo que el tool-calling actual.
2. **NL→Cypher con esquema.** Dar a Groq el contrato de `schema.cypher` +
   `CALL db.schema.visualization` + 8-10 ejemplos few-shot; escribe Cypher;
   ejecutar en solo lectura con `access_mode=READ`, timeout de sentencia y
   un guard que rechace `CREATE|MERGE|DELETE|SET|REMOVE|CALL .*\.(create|
   write|delete)`. Herramienta MCP `consulta_grafo`. Techo más alto, el
   guard tiene que ser estricto.
3. **Herramientas analíticas APOC/GDS.** `ruta_grafo` llamando
   `apoc.algo.dijkstra` server-side (retira las 2 reimplementaciones Python
   de Dijkstra — esto es FIL_54, ya desbloqueado). Un `analisis_grafo` sobre
   `gds.session` para centralidad/comunidad bajo demanda (ojo: provisionar
   sesión tiene suelo de coste).

Además: endpoint de solo lectura `GET /grafo/consulta` en la API del
asistente para que la web y el mapa toquen el grafo directamente.

### C. Endurecimiento (antes de nada de cara al usuario) — FIL_67k

- Credenciales **rol lector** de Aura para la vía de consulta (separadas de
  las del loader).
- Timeout de sentencia + `access_mode=READ` + conciencia del límite de
  conexiones (Aura Free).
- Solo parámetros, nunca Cypher interpolado con strings.

---

## Parte 3 — Capa de presentación

El cambio de más impacto: **que el mapa muestre el grafo real.**

| # | Mejora | Notas | Ticket |
|---|---|---|---|
| 1 | **Alimentar `viz/mapa` desde `grafo_urbano.json.gz`** (o lectura Neo4j en tiempo de build) en vez del `coords-knn8` del STGNN. Habilita capas nuevas: estaciones meteo, recintos, capacidad bicimad, cobertura de contaminantes, coropleta por `subarea`. Unifica los "dos grafos". | M | FIL_67l |
| 2 | **Panel "Explorar" en la web** — clic en un lugar → renderiza su vecindario de grafo: todos los sensores cercanos por tipo, su barrio/distrito, recintos/parques cerca, líneas en las paradas próximas. Es `contexto_urbano` hecho visual. | necesita `GET /grafo/consulta` | FIL_67m |
| 3 | **Capa de ruta en vivo** — ruta saludable dibujada desde una llamada `apoc.algo.dijkstra` server-side, no un JSON precalculado. | depende de FIL_54 | FIL_67n |
| 4 | **Overlay de resiliencia** (FIL_64) — puntos de articulación / puentes de la red de transporte como capa conmutable del mapa. Visual fuerte para la defensa. | dato ya calculado (`grafo_resiliencia.json`) | FIL_67o |
| 5 | **Procedencia en el chat** — cuando el asistente responde "aire cerca de Retiro", mostrar qué estación usó y el camino `PROXIMO_A`, como mini-grafo bajo la burbuja. | ata el grafo a cada respuesta | FIL_67p |
| 6 | **Pestaña "grafo en crudo"** — embeber Neo4j Bloom / Browser (Aura), creds de rol lector. | mínimo esfuerzo, enseña la cosa real | FIL_67q |

---

## Secuenciación sugerida (deadline 2026-09-17)

1. **Ahora:** Parte 2A (acceso dev) + Parte 1 #1, #4, #6 (cableado pequeño y
   de alto valor con dato ya cargado).
2. **Siguiente:** Parte 2B opción 1 (librería parametrizada) + Parte 3 #1
   (mapa desde el grafo real) + #4 (overlay de resiliencia).
3. **Si hay tiempo:** FIL_54 (`apoc.algo.dijkstra` como herramienta) → Parte
   3 #3; Parte 1 #5 (`:Linea`); Parte 3 #2/#5 (panel explorar + procedencia).
4. **Pulido de defensa:** Parte 3 #6 (pestaña Bloom); capítulo de grafo de
   la memoria con los hallazgos de FIL_52/64.

## Restricciones

- Python puro en `grafo/`. `allow_infra_apply: false`. La única escritura a
  Neo4j es la (re)carga; todo lo demás es solo lectura.
- Las creds de la instancia siguen en SSM (`/madrono-tfm/dev/secrets/
  neo4j-*`); el nombre real de la base es `5c111cec`, no `neo4j`.

---

## Progreso — Paso 1 (2026-09-09)

**Parte 2A (acceso dev) — hecho:**
- `NEO4J_DATABASE` por defecto `"neo4j"` → `None` (home DB) en
  `asistente/neo4j_client.py`, `grafo/cargar_grafo.py`,
  `grafo/cypher.py::Neo4jLoader`. Ya no hace falta pasar el nombre real.
- **`grafo/consulta.py`** — CLI de solo lectura (creds de env o SSM,
  `session(default_access_mode='READ')`, guard anti-escritura). Probado en
  vivo: `python -m grafo.consulta "MATCH (e:EstacionMedida) RETURN e.tipo,
  count(*)"` sin `NEO4J_DATABASE` funciona.
- Tests: `grafo/tests/test_consulta.py` (guard + parseo SSM).

**Parte 1 #1 (aire por contaminante) — constructor listo:**
- `asistente/neo4j_client.py::estaciones_calidad_aire_que_miden_query(lugar,
  contaminante, radio_m)` — filtra `PROXIMO_A` a estaciones con
  `toUpper($contaminante) IN e.contaminantes`. Test en
  `asistente/tests/test_neo4j_client.py`. **Pendiente:** cablearlo en la
  herramienta `calidad_aire` (`asistente/mcp_agent/tools.py`) cuando se pida
  un contaminante concreto.

**Extra (utilizar todo): `nombre` de estación ahora se persiste.**
`estacion_medida_query` / `parada_transporte_query` guardaban
`tipo`/`fuente`/`ubicacion` pero **no** `nombre`, así que `e.nombre` era
siempre `null` para calidad_aire/ruido/meteo pese a que `grafo.nodos` lo
construye. Corregido (`SET n.nombre = $nombre`); la próxima recarga lo
rellena. `schema.cypher` actualizado.

Suite `grafo/` + `asistente/` verde (298).

**Recarga hecha** (2026-09-09, 9,4 min, rc=0): `nombre` ahora poblado en las
162 estaciones con nombre en Gold (aforos 83 / ruido 31 / meteo 25 /
calidad_aire 23); tráfico sigue sin nombre (Gold no lo trae). Demo:
`grafo/consulta.py "MATCH (e:EstacionMedida {tipo:'calidad_aire'}) RETURN
e.nombre, e.contaminantes"` → "Casa de Campo: NO,NO2,NOx,O3,PM10,PM2.5".

**Cerrado el Paso 1** (2A + #1 + fix de `nombre`). CI de #248 en verde.

## Progreso — Paso 2 (2026-09-09)

**Parte 1 #3 (meteo como vecino de primera clase) + exponer FIL_66 en
`contexto_urbano` — hecho:**
- `asistente/modelos/grafo_urbano.json.gz` re-sincronizado desde
  `grafo/_data/` (tenía la copia de 31/8, sin meteo/recintos/atributos).
- `asistente/contexto_urbano.py`: `_cargar` captura los atributos estáticos
  (`contaminantes`, `magnitudes`, `altitud_m`, `anclajes_totales`,
  `plazas_totales`, `subarea`) y el `linea`/`modo` de cada arista
  `CONECTADO_CON`. `contexto()`:
  - `estaciones_1_salto` incluye ahora **`meteo`** + arrastra el atributo
    estático de cada estación + su `nombre` (FIL_67).
  - `lugares_cercanos_2_saltos` incluye **`recinto`** + `plazas_totales` en
    aparcamientos.
  - campo nuevo **`lineas_cercanas`** = líneas de transporte que pasan por
    la vecindad de `CONECTADO_CON` (≤2 saltos de la parada ancla).
- Modelos `EstacionProxima` (+`nombre`/`contaminantes`/`magnitudes`/
  `altitud_m`/`subarea`) y `ContextoUrbano` (+`lineas_cercanas`); router y
  wrapper MCP cableados; docstring de la tool actualizado.
- Verificado en vivo: `contexto_urbano("Sol")` → estación de aire "Plaza
  del Carmen" con `contaminantes=[CO,NO,NO2,NOx,O3,SO2]`, meteo "Plaza del
  Carmen" `magnitudes=[humidity_pct,temperature_c] altitud_m=660`, tráfico
  `subarea=110007`, `lineas_cercanas=[metro 2]`, recintos "Teatro Eslava"…,
  aparcamientos con `plazas_totales`.
- Tests `test_contexto_urbano.py` +1 (`test_enriquecimiento_fil65_fil66`).
  Suite `asistente/` + `grafo/` verde (299).

**Nota sobre Parte 1 #4 (`prevision_ciudad`):** revisado el dato real —
`aemet_prevision_por_municipio_leadtime` NO es una previsión puntual sino un
**promedio histórico por leadtime** sobre la ventana recogida (4 filas: 1
municipio × leadtime 0-3; `avg_temperature_max_c` etc.), y ambas tablas
(CAMS + AEMET) están congeladas (datos hasta ~2026-08-30). Valor bajo para
una herramienta "previsión de ciudad" con ese shape y esa frescura. Bajar
prioridad; si se hace, servir sobre todo CAMS (`fecha_validez` + µg/m³ por
contaminante, sí es utilizable) y etiquetar la respuesta como
"último forecast disponible (pipeline congelado)".

**Parte 2B opción 1 (librería de consultas parametrizadas + tool
`consulta_grafo`) — hecho:**
- `asistente/neo4j_client.py`: 6 constructores nuevos —
  `vecindario_de_lugar_query` (todo a `radio_m`, con contaminantes/
  magnitudes/subárea/capacidades), `estaciones_meteo_cerca_query`,
  `recintos_cerca_query`, `aparcamientos_cerca_query`,
  `bicimad_cerca_query`, `lineas_que_pasan_por_query`,
  `paradas_de_linea_query` (+ `estaciones_calidad_aire_que_miden_query` del
  Paso 1).
- **Herramienta MCP nº 15 `consulta_grafo`** (`asistente/mcp_agent/tools.py`
  `_PLANTILLAS_GRAFO`): 8 plantillas de **solo lectura** elegidas por
  nombre (no Cypher libre). Contrato `FIL_15`: plantilla desconocida /
  parámetros que falten / Neo4j caído → `disponible=false` + `motivo` +
  `plantillas_disponibles`, nunca excepción. Modelo `ConsultaGrafo`;
  registrada en `server.py`; router `GET /consulta-grafo`.
- Tests: `test_consulta_grafo.py` nuevo + `test_neo4j_client.py` +7;
  `test_mcp_tools` / `test_mcp_transport` actualizados a 15 tools. Suite
  `asistente/` + `grafo/` verde (310).
- Verificado en vivo: `consulta_grafo(plantilla="bicimad_cerca",
  lugar="Sol")` → "33 - Puerta del Sol" `anclajes_totales=43` a 23 m;
  `plantilla="paradas_de_linea", linea="6", modo="metro"` → 28 paradas con
  coords; `meteo_cerca`/`recintos_cerca` OK.

**Parte 3 #2 (explorador del grafo real) — hecho, sin tocar el mapa animado:**
- `viz/build_grafo_explorador.py` → `viz/grafo_explorador.html` — página
  autónoma (un HTML, `file://` OK) con maplibre-gl que pinta el grafo REAL
  de Neo4j: 9.624 nodos de los 5 labels (meteo/recintos incluidos), 3.947
  tramos `CONECTADO_CON`, capas conmutables por tipo, y clic en un nodo →
  panel con atributos de FIL_66 (`contaminantes`/`magnitudes`/`altitud`/
  `subarea`/capacidades), barrio/distrito reales, líneas de transporte y
  vecindario `PROXIMO_A` (dibujado al vuelo). Offline desde
  `grafo/_data/grafo_urbano.json.gz`; **cero cambios en `viz/mapa/` / app
  web / gh-pages**.
- Tests `tests/test_grafo_explorador.py` (4). `viz/README.md` actualizado.

Decisión: **no** reescribir la fuente de datos del mapa animado
(`build_mapa_animado.py`, deliverable fusionado y en vivo) a estas alturas
del calendario — el explorador autónomo cubre "ver el grafo real" con riesgo
nulo. Parte 3 #1 (mapa animado desde el grafo real) y #4 (overlay de
resiliencia sobre él) quedan como mejora post-entrega.

**QA:** ver `VIC_34`–`VIC_38` (grafo, `consulta_grafo`, analítica de
resiliencia, consistencia 15 tools, integración en memoria).

**Parte 3 #2 (v2) — explorador EN VIVO — hecho:**
- `viz/build_grafo_explorador.py --live` → `viz/grafo_explorador_live.html`
  (~9 KB, sin grafo embebido): pide el grafo a la app del asistente.
- `asistente/routers/grafo_explorador.py`: `GET /grafo/explorador` (HTML),
  `GET /grafo/explorador/data` (nodos + `CONECTADO_CON` + líneas, leído de
  Neo4j, cacheado 10 min), `GET /grafo/explorador/vecindario?id=` (vecinos
  `PROXIMO_A` de un nodo, al hacer clic). Fallo de Neo4j → 503 legible.
- `asistente/neo4j_client.py`: `grafo_explorador_nodos_query`,
  `grafo_explorador_conectado_con_query`, `vecindario_grafo_query`.
- Montado en `asistente/main.py`. Tests
  `asistente/tests/test_grafo_explorador_router.py` +
  `tests/test_grafo_explorador.py` (variante live).
- **Verificado en vivo** contra Neo4j real vía `TestClient`: `/data` →
  9.651 nodos / 3.947 tramos / 3.375 con líneas en 5,2 s (luego cache);
  `/vecindario` de una estación de aire → 10 vecinos
  (bicimad/emt/ruido/trafico).
- El `grafo_explorador.html` autónomo (grafo embebido) se mantiene para uso
  `file://` sin backend.

**Parte 3 #2 (v3) — menú + análisis del TFM sobre el grafo — hecho:**
- Menú `Vista / análisis` (select) con 6 vistas que re-colorean/anotan el
  grafo:
  1. **Explorar** — color por tipo (defecto).
  2. **Aire · cobertura** — estaciones de tráfico verde/rojo según tengan o
     no una estación de aire a ≤300 m. Panel: **4.525 / 4.705 (96 %)** sin
     aire cerca (solo 23 estaciones de aire para toda la ciudad).
  3. **Aire · qué mide cada estación (FIL_66)** — estaciones de aire azul si
     miden O₃, rojo si no.
  4. **Sensores por distrito (§7)** — tabla distrito × total/tráfico/aire;
     el sesgo (Fuencarral 544 vs Vicálvaro 62).
  5. **Transporte · resiliencia (FIL_64)** — 683 puntos de articulación
     resaltados (casados por nombre→`:ParadaTransporte`), + nº de puentes,
     k-core, curva de robustez y el caveat `_nota`.
  6. **Modelo STGNN · aristas influyentes (ML_05)** — las 15 conexiones más
     influyentes como arcos con grosor ∝ importancia.
- `GET /grafo/explorador/analisis` (cacheado 10 min): cobertura de aire y
  sensores/distrito **en vivo desde Neo4j**
  (`cobertura_aire_query`/`sensores_por_distrito_query`), + aristas STGNN de
  `stgnn_trafico.meta.json`, + resiliencia de `grafo_resiliencia.json`
  (FIL_64). En modo embebido, cobertura y distrito se derivan en el cliente
  de `PROX`/`N`. Fallo de Neo4j → 503.
- Verificado en vivo: `/analisis` → cobertura 4525/4705, 21 distritos,
  15 aristas STGNN (`trafico:5412↔trafico:5768` w=1.0), 683 puntos de
  articulación. Menú y panel renderizan (screenshot headless).
- Tests actualizados; `<script>` válido (`node --check`).
