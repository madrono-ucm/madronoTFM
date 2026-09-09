---
kind: fil
title: "Enriquecer nodos del grafo con atributos estáticos que ya están en Gold (cobertura de contaminantes, capacidades, subárea…)"
owner: Filippos (interactive)
status: in_review
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_65]
milestone: "M7"
target: "2026-09-14"
---

## Progreso (2026-09-09) — código + tests listos y verificados en vivo

- `grafo/extract.py`: `_split_csv` helper; los 7 `fetch_*` añaden las columnas
  nuevas (`array_join(array_sort(array_agg(DISTINCT …)))` para las listas,
  `max_by(…, date)` para los escalares).
- `grafo/nodos.py`: `_with_optional` helper (omite `None`/`[]`); las 7
  funciones `*_from_*_gold` suben el atributo al `dict`.
- `grafo/cypher.py`: `_extra_props` + `SET n += $extra` en
  `estacion_medida_query` / `parada_transporte_query` / `lugar_query` — así
  cualquier atributo estático nuevo se persiste sin volver a tocar cypher.
- `infra/neo4j/schema/schema.cypher`: propiedades opcionales documentadas.
- Tests: `grafo/tests/` +16 (nodos / extract / cypher). Suite `grafo/` verde
  (128).
- **Verificado en vivo (solo lectura Athena)** las 7 consultas:
  `contaminantes` p. ej. Plaza del Carmen = [CO,NO,NO2,NOx,O3,SO2];
  `subarea` en 4678 puntos; `docks_total`, `total_spaces`, `altitude_m`,
  `modos`, `magnitudes` OK.
- **`grafo_urbano.json.gz` regenerado** con los atributos visibles.

**Pendiente:** re-cargar la instancia AuraDB (`grafo.cargar_grafo` vía el
runner de sesión) para que los nodos ya existentes reciban las propiedades
nuevas (`MERGE … SET n += $extra`, idempotente).

## Motivación

Auditoría de las 15 tablas Gold contra el grafo (2026-09-09): varios nodos
ya existen pero Gold trae **atributos estáticos por entidad** que el nodo no
guarda. No hace falta reingesta ni descongelar el pipeline — el dato ya está
en Gold, solo hay que subirlo al `dict` del nodo (mismo patrón puro de
`grafo/nodos.py`).

El más valioso: **cada estación de calidad del aire mide un subconjunto
distinto de contaminantes** (verificado en vivo: `28079011` solo mide
NO/NO2/NOx; `28079008` mide 11). Hoy `PROXIMO_A` a
`:EstacionMedida {tipo:'calidad_aire'}` devuelve la estación más cercana sea
cual sea el contaminante — no se puede pedir "la estación más cercana que
mida O₃". Con una propiedad `contaminantes` en el nodo, sí.

## Alcance — solo propiedades nuevas, cero labels/relaciones nuevas

| Nodo | Propiedad nueva | Origen Gold (columna) |
|---|---|---|
| `:EstacionMedida{calidad_aire}` | `contaminantes: [string]` | `calidad_aire_..._contaminante_hora.pollutant` (`array_agg distinct`) |
| `:EstacionMedida{meteo}` | `magnitudes: [string]` | `meteorologia_..._magnitud_hora.magnitude` (`array_agg distinct`) |
| `:EstacionMedida{meteo}` | `altitud_m: int` | `meteorologia_....altitude_m` |
| `:EstacionMedida{ruido}` | `altitud_m: int` | `ruido_..._periodo_fecha.altitude_m` |
| `:EstacionMedida{trafico}` | `subarea: string` | `trafico_por_punto_hora.subarea` (315 zonas de gestión) |
| `:EstacionMedida{aforos}` | `modos: [string]` | `aforos_..._modo_hora.mode` (peatones / bicicletas) |
| `:ParadaTransporte{bicimad}` | `anclajes_totales: int` | `bicimad_por_estacion_hora.docks_total` |
| `:Lugar{aparcamiento}` | `plazas_totales: int` | `aparcamientos_por_parking_hora.total_spaces` |

Cambios:
- `grafo/extract.py`: añadir las columnas nuevas a los `SELECT`/`GROUP BY` de
  `fetch_estaciones_calidad_aire`, `fetch_estaciones_meteo`,
  `fetch_estaciones_ruido`, `fetch_estaciones_trafico`,
  `fetch_estaciones_aforos_peatones_bicicletas`, `fetch_paradas_bicimad`,
  `fetch_lugares_aparcamientos`. Para las listas: `array_agg(distinct col)`
  → Athena la devuelve como texto `[a, b, c]`; parsear a `list[str]` en
  `extract` (helper `_parse_athena_array`, mismo criterio que
  `_cast_athena_value`).
- `grafo/nodos.py`: cada `*_from_*_gold` añade la clave nueva al `dict` (o la
  omite si el registro no la trae — defensivo, como `nombre`).
- `grafo/cypher.py`: los `MERGE` de nodo hacen `SET n += row` o enumeran
  propiedades — revisar que las nuevas se persistan (si enumera, añadirlas).
- `infra/neo4j/schema/schema.cypher`: documentar las propiedades opcionales
  nuevas por label (igual que ya se hizo con `osm_*` en `:Lugar`).
- `grafo/exportar_grafo.py`: sin cambio de estructura (reusa las mismas
  funciones); el artefacto recogerá las propiedades nuevas al regenerarse.
- Tests en `grafo/tests/test_nodos.py` + `test_extract.py`.

## Fuera de alcance (documentado, no se hace aquí)

- **`:Linea` + `PARA_EN`**: el `linea`/`modo` ya vive como propiedad de las
  aristas `CONECTADO_CON`. "Qué líneas pasan por la parada X" y "paradas de
  la línea 6" **ya son consultables hoy**
  (`MATCH (p)-[r:CONECTADO_CON]-() RETURN DISTINCT r.linea, r.modo`), así que
  un nodo `:Linea` es normalización/comodidad, no capacidad nueva. Se puede
  hacer más adelante; no bloquea nada.
- **`:ZonaAviso`** (avisos AEMET): Gold `aemet_avisos_por_zona_fecha_nivel`
  tiene 3 zonas ("Metropolitana y Henares" = ciudad de Madrid, + Sierra +
  Sur/Vegas/Oeste), pero el mapeo zona→distrito no está en Gold (es
  conocimiento externo: la ciudad entera cae en "Metropolitana y Henares").
  Valor bajo (una propiedad constante en los 21 distritos) y la tabla está
  congelada/rala por naturaleza. Se deja anotado.
- Reingesta de las Gold incompletas (`aforos` fuente muerta 2024-06-30;
  `transporte_publico_emt` 1 parada = FIL_07; `cartelera_cines` 2 salas sin
  coordenadas en origen). Ninguna aporta al grafo lo suficiente para
  justificar descongelar el pipeline — análisis en el hilo de la sesión.

## Criterios de aceptación

- Suite `grafo/` verde; tests nuevos cubren: propiedad presente cuando Gold
  la trae, ausente/None cuando no, y el parseo de `array_agg` a lista.
- `python -m grafo.exportar_grafo` regenera el artefacto con las propiedades
  nuevas visibles en `_meta` o inspeccionables.
- La carga real (`grafo.cargar_grafo` vía el runner de sesión) es el paso
  final; `MERGE ... SET` es idempotente, no duplica nada.

## Restricciones

- Python puro en `nodos.py`/`relaciones.py`. `allow_infra_apply: false`.
- Solo lectura de Athena para `extract`; la única escritura es la carga
  final a Neo4j.
