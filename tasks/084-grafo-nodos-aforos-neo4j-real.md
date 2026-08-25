---
id: 84
slug: grafo-nodos-aforos-neo4j-real
title: 'Grafo: añadir EstacionMedida{tipo: aforo} y recargar la instancia real'
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: null
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

`asistente/mcp_agent/tools.py::afluencia_prevista` está bloqueada por
`GOOGLE_MAPS_API_KEY` (no disponible en este entorno, ver su docstring y
`doc/012`). Decisión tomada: en vez de esperar esa credencial, se sustituye
la señal de afluencia por `aforos_peatones_bicicletas` (tarea 013/054) —
conteos horarios reales de peatones/bicicletas en estaciones fijas del
Ayuntamiento, dato oficial, gratuito, ya en producción en
`gold.aforos_peatones_bicicletas_por_estacion_modo_hora`, sin ningún
bloqueo de credencial.

Para que la futura tool pueda cruzar `:Lugar` con estaciones de aforo por
proximidad (mismo patrón que `trafico_cercano`, tarea 081), el grafo
necesita un nuevo tipo de `:EstacionMedida` que hoy no existe:
`tipo: "aforo"`. Esta tarea es **solo la parte de grafo** (extracción +
carga real) — la tool del asistente (`afluencia_prevista`) es la tarea
`085`, deliberadamente separada y numerada después porque depende de que
esta se fusione primero.

Ver `grafo/extract.py::fetch_estaciones_trafico`/`fetch_estaciones_calidad_aire`
y `grafo/nodos.py::estacion_medida_from_trafico_gold`/`..._calidad_aire_gold`
como plantilla exacta a replicar — mismo patrón, tercer origen de
`:EstacionMedida` además de `trafico`/`calidad_aire`/`ruido`.

**Esquema real de Gold** (`procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`):
tabla `aforos_peatones_bicicletas_por_estacion_modo_hora`, columnas
relevantes `station_id`, `mode` (`"peatones"`/`"bicicletas"` —
`station_id` ya es único por estación, no hace falta agrupar por `mode`
para identificar el nodo, ver el docstring de `aggregate.py`), `district`,
`address`, `date` (partición), `hour`, `location.lat`/`location.lon`
(struct anidado, no columnas planas como en `trafico_por_punto_hora` —
ajusta el SQL para acceder a `location.lat`/`location.lon`).

Credenciales de Neo4j en SSM (`/madrono-tfm/dev/secrets/neo4j-{uri,username,
password,database}`, región `eu-west-1` explícita — ver el bug corregido en
`PLAN.md`), mismo patrón que las tareas `080`/`081`. `force: false`
deliberado: esta tarea escribe en el grafo de producción real.

## Objetivo

Añadir `:EstacionMedida {tipo: "aforo"}` al pipeline de extracción/carga
del grafo, y recargar la instancia real de Neo4j para que estos nodos (y
sus relaciones `PROXIMO_A` con `:Lugar`) existan de verdad.

## Alcance concreto

1. `grafo/extract.py`: añade `fetch_estaciones_aforos(athena_client=None)`
   — un registro por `station_id` con su ubicación más reciente (mismo
   `_recent_date_filter()`/ventana que `fetch_estaciones_trafico`), leyendo
   `location.lat`/`location.lon` de la tabla real (ajusta `_nest_location`
   o el SQL si la estructura anidada lo requiere — revísalo contra el
   esquema real de Athena antes de asumir la forma exacta). Incluye
   `address`/`district` en el `SELECT` para usarlos como `nombre`.
2. `grafo/nodos.py`: añade `estacion_medida_from_aforos_gold(record)` (id
   `f"aforo:{station_id}"`, `tipo: "aforo"`, `fuente: "aforos_peatones_bicicletas"`,
   `nombre`: `address` si existe, si no `district`, si no `None`) y su
   plural `estaciones_medida_from_aforos_gold`, mismo patrón que las otras
   tres funciones de esta sección.
3. `grafo/cargar_grafo.py::cargar_grafo`: añade
   `+ nodos.estaciones_medida_from_aforos_gold(extract.fetch_estaciones_aforos())`
   a la construcción de `estaciones_medida` — no hace falta tocar
   `relaciones.py` (`PROXIMO_A`/`UBICADO_EN` ya son genéricas sobre
   cualquier nodo con ubicación de tipo distinto, ver `grafo/relaciones.py`).
4. Tests: `grafo/tests/test_extract.py` y `grafo/tests/test_nodos.py`,
   mismo patrón que los de `calidad_aire`/`ruido` en esos ficheros.
5. **Recarga real**: ejecuta `python3 -m grafo.cargar_grafo` contra la
   instancia real (credenciales de SSM en tiempo de ejecución) — es
   idempotente (`MERGE`, ya verificado en la tarea `080`), no borres nada
   antes. Verifica con Cypher real: conteo de `EstacionMedida {tipo:
   'aforo'}` > 0, y que el conteo total de `PROXIMO_A` ha aumentado
   respecto a los 41031 de la tarea `080`.
6. `grafo/README.md`: añade `aforo` a la tabla de orígenes de
   `:EstacionMedida` y actualiza los conteos reales.
7. Documenta en `doc/084-grafo-nodos-aforos-neo4j-real.md` el esquema real
   de Athena encontrado, la recarga realizada, y los conteos finales.

## Restricciones

- No implementes aquí la tool `afluencia_prevista` ni toques
  `asistente/` — es la tarea `085`, deliberadamente separada y posterior.
- No toques `ingesta/capturas/afluencia_lugares_madrid.py` (tarea 012) ni
  `populartimes` — quedan documentados como están, no se borran.
- No cambies el umbral de `PROXIMO_A` (300m, tarea 070) ni reabras esa
  decisión.

## Criterios de aceptación

- `:EstacionMedida {tipo: 'aforo'}` existe en la instancia real de Neo4j
  con un conteo > 0, verificado con Cypher real.
- `PROXIMO_A` incluye relaciones nuevas hacia esos nodos (conteo total
  aumentado respecto a `080`), verificado con Cypher real.
- Tests en verde.
- `grafo/README.md` y `doc/084-...md` reflejan el esquema real y los
  conteos reales tras la recarga.
