---
kind: fil
title: "Cerrar huecos medallion→grafo: nodos :EstacionMedida{meteo} y :Lugar{recinto} desde Gold/Silver"
owner: Filippos (interactive)
status: in_review
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_08]
milestone: "M7"
target: "2026-09-14"
---

## Progreso (2026-09-09) — código listo y verificado en vivo; falta la carga

- `grafo/nodos.py`: `estacion_medida_from_meteo_gold` / `..._plural`,
  `lugar_from_recinto_evento` / `..._plural` + `_slug_recinto` (Python puro).
- `grafo/extract.py`: `fetch_estaciones_meteo` (Gold, sin ventana reciente)
  y `fetch_recintos_eventos_silver` (Silver `agenda_eventos`, `GROUP BY
  venue_name`).
- Cableado en `grafo/cargar_grafo.py` y `grafo/exportar_grafo.py`.
- `infra/neo4j/schema/schema.cypher`: comentarios de `:EstacionMedida`
  (`tipo` += `"meteo"`) y `:Lugar` (`tipo` += `"recinto"`, fuente
  `agenda_eventos`).
- Tests: `grafo/tests/test_nodos.py` (+6) y `test_extract.py` (+2). Suite
  `grafo/` verde (113).
- **Verificado en vivo contra Athena real** (solo lectura):
  `fetch_estaciones_meteo()` → **25 estaciones** (Plaza del Carmen, Barrio
  del Pilar, Juan Carlos I, …, con lat/lon reales);
  `fetch_recintos_eventos_silver()` → **145 recintos** (Ciudad Real Madrid,
  Gran Teatro CaixaBank Príncipe Pío, Coliseum, parques, polideportivos…).

**Pendiente (gated, requiere OK humano):**
1. `python -m grafo.exportar_grafo` (necesita AWS) → regenerar
   `grafo/_data/grafo_urbano.json.gz` con los dos labels nuevos, y volver a
   correr `FIL_52`/`FIL_64` para que los recojan.
2. `python -m grafo.cargar_grafo` contra la instancia AuraDB real — escribe
   en la instancia que leen el mapa publicado y el asistente público, 20–50
   min (tier Free), histórico de `SessionExpired` (`FIL_08`). Ventana
   tranquila + `git pull` + verificación post-carga de los counts nuevos.

## Motivación

Inventario en vivo de la instancia AuraDB real (`5c111cec`, 2026-09-09):
**15 tablas Gold**, pero varias entidades fijas y geolocalizadas de la
medallion **no tienen ningún nodo en el grafo**:

| Gold / Silver | Entidad fija con lat/lon | ¿En el grafo hoy? |
|---|---|---|
| `meteorologia_por_estacion_magnitud_hora` (Gold) | estaciones meteo (`station_id`, `station_name`, `lat`, `lon`, `altitude_m`) | **NO** |
| `agenda_eventos` (Silver: `venue_name`, `lat`, `lon`, `district`) | recintos / lugares de eventos | **NO** (`:Evento`/recinto inexistente) |
| `afluencia_lugares_por_lugar_fecha_hora` (Gold) | — (serie temporal por `lugar_id`) | correcto que NO sea nodo (serie), ya cruzable por `lugar_id` |

Consecuencias concretas hoy:
- La meteo solo llega al sistema como un *join haversine* a la estación más
  cercana en `modelado/features/exogenas.py`. En el grafo no es vecina
  `PROXIMO_A` de tráfico/ruido/aire como sí lo son las otras estaciones —
  aunque es exactamente el mismo patrón de "punto de medida fijo".
- `eventos_cercanos` (tool MCP) hace haversine en Python contra **Silver**
  porque no hay ningún recinto en el grafo contra el que hacer `MATCH ...
  PROXIMO_A`. El resto de tools de "cerca de X" sí atraviesan el grafo.

Este ticket añade los dos tipos de nodo que faltan, con el mismo patrón puro
y testado de `grafo/nodos.py` (`<tipo>_from_<origen>` / `<tipo>s_from_<origen>`
+ dedupe), y su cableado en `extract.py` / `cargar_grafo.py`.

## Alcance

### 1. `:EstacionMedida {tipo: "meteo"}`

- `grafo/extract.py`: `fetch_estaciones_meteo(athena_client=None)` —
  `SELECT DISTINCT station_id, station_name, lat, lon, altitude_m FROM
  meteorologia_por_estacion_magnitud_hora` (patrón idéntico a
  `fetch_estaciones_ruido`; `_nest_location` para `{lat, lon}`).
- `grafo/nodos.py`: `estacion_medida_from_meteo_gold` / `..._plural`.
  `id = "meteorologia:<station_id>"`, `tipo = "meteo"`, `fuente =
  "meteorologia"`, `nombre = station_name`, `ubicacion = {lat, lon}`.
  (`altitude_m` NO se guarda: `schema.cypher` no declara altitud para
  `:EstacionMedida` y ninguna consulta la usa — mantener el contrato.)
- `infra/neo4j/schema/schema.cypher`: ampliar el comentario de
  `:EstacionMedida` (`tipo` admite ahora `"meteo"`) — sin cambio de
  constraint/índice (ya existen sobre `id`/`tipo`/`ubicacion`).
- Entra en `UBICADO_EN` y `PROXIMO_A` automáticamente (son genéricas sobre
  "cualquier nodo con `ubicacion`, `tipo` distinto"), sin tocar
  `relaciones.py`.

### 2. `:Lugar {tipo: "recinto"}`

- `grafo/extract.py`: `fetch_recintos_eventos_silver(...)` — lee **Silver**
  `agenda_eventos` (no Gold: la Gold agrega por categoría/distrito/fecha y
  pierde `venue_name`/lat/lon; ver el docstring de
  `asistente/neo4j_client.py::resolver_lugar_query`). Devuelve filas
  `{venue_name, lat, lon, district}` con coords no nulas.
  - Silver se lee vía Athena igual que Gold (misma `GOLD_DATABASE`→
    parametrizar a `SILVER_DATABASE`, o `run_athena_query(sql,
    "madrono-tfm_dev_silver", ...)`).
- `grafo/nodos.py`: `lugar_from_recinto_evento` / `..._plural`. Clave de
  negocio = `venue_name` normalizado (no hay `venue_id` en Silver);
  `id = "agenda_eventos:" + slug(venue_name)`, `tipo = "recinto"`,
  `fuente = "agenda_eventos"`, `nombre = venue_name`, `ubicacion = {lat,
  lon}`. Dedupe por `id` (varios eventos comparten recinto).
  - Si un mismo `venue_name` aparece con coords ligeramente distintas entre
    eventos, se queda con el primero visto (criterio ya usado por
    `dedupe_nodes`); documentar la limitación en el docstring.
- `schema.cypher`: `:Lugar.tipo` admite ahora `"recinto"` (el comentario ya
  anticipaba "recinto" para `agenda_grandes_recintos_madrid`; aquí la fuente
  es `agenda_eventos`) — actualizar el comentario.

### 3. Cableado

- `grafo/cargar_grafo.py`: añadir las dos fuentes al encadenado
  extract→nodos→(ubicado_en/proximo_a)→cypher, en el mismo punto donde ya
  se procesan ruido/aforos/aparcamientos. Los `MERGE` existentes
  (`cypher.estacion_medida_query` / `lugar_query`) sirven sin cambios (mismo
  contrato de propiedades).
- `grafo/exportar_grafo.py` (`FIL_51`): incluir los dos nuevos orígenes para
  que el artefacto offline (`grafo_urbano.json.gz`) y por tanto `FIL_52`/
  `FIL_64` los vean.

## Fuera de alcance

- **`:Evento` como nodo por evento**: los eventos son entidades con ventana
  temporal; el grafo modela entidades estables (mismo principio por el que
  las series de medidas viven en Gold/Athena, no en Neo4j). El recinto sí es
  estable. `eventos_cercanos` seguirá leyendo la lista de eventos de Silver;
  lo que gana es poder resolver el punto de referencia y los vecinos contra
  el grafo.
- `afluencia_lugares`: es una serie derivada por `lugar_id` ya existente,
  cruzable con los `:Lugar` actuales por id. No se modela.
- Reingesta / descongelado del pipeline. Se trabaja sobre los datos Gold/
  Silver ya presentes.

## Criterios de aceptación

- `grafo/tests/test_nodos.py` + `test_extract.py` cubren las funciones
  nuevas con fixtures (patrón existente): registro válido → dict correcto;
  registro sin clave de negocio → `None`; dedupe de recinto por nombre.
- `python -m grafo.exportar_grafo` (offline, necesita AWS) regenera
  `grafo_urbano.json.gz` con los dos labels nuevos representados.
- Suite `grafo/` verde.
- **La carga real** (`python -m grafo.cargar_grafo` contra la instancia
  AuraDB) queda como **último paso, con confirmación humana explícita**:
  escribe en la instancia que leen el mapa publicado y el asistente público,
  tarda 20–50 min (tier Free) y ya tuvo incidencias de `SessionExpired`
  (`FIL_08`). Antes de lanzarla: `git pull`, ventana tranquila, y
  verificación post-carga de los counts nuevos (`MATCH (e:EstacionMedida
  {tipo:'meteo'}) RETURN count(*)` etc.).

## Restricciones

- `grafo/nodos.py` y `grafo/relaciones.py` siguen siendo Python puro (sin
  `import neo4j`), testables sin driver ni conexión.
- `allow_infra_apply: false`. El único paso que toca la instancia real es la
  carga final, y requiere OK humano en el momento.
