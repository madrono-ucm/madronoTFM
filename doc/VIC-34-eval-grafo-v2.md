# VIC_34 — Evaluación del grafo real tras FIL_65/66/67 (2026-09-10)

Verificación agregada de la instancia AuraDB Free tras las 3 cargas de la
sesión del 2026-09-09 (FIL_65: nodos meteo/recinto; FIL_66: atributos
estáticos de Gold; FIL_67: `nombre` persistido). Todas las consultas de
abajo son de solo lectura, vía `python -m grafo.consulta` (credenciales
reales por SSM, region `eu-west-1`) y una consulta Athena directa de
verificación puntual. Nota metodológica encontrada en el camino: el rol de
esta EC2 (`madrono-terraform-deployerEC2`) ya tiene todo lo necesario —
**no hace falta `AWS_PROFILE=madrono`** (ese perfil no existe en esta
máquina; forzarlo rompe la resolución de credenciales SSM del propio
`grafo/consulta.py`, que cae en silencio al mensaje "sin credenciales").

## 1. Conteos — ✅ coherentes, con una explicación necesaria

Total real: **9806 nodos** (`EstacionMedida` 4867, `ParadaTransporte` 4056,
`Lugar` 731, `Barrio` 131, `Distrito` 21) y **76002 relaciones**
(`PROXIMO_A` 54380, `CONECTADO_CON` 11998, `UBICADO_EN` 9493,
`PERTENECE_A` 131). Coincide con el "~9.806 nodos / ~76k rels" reportado
por las cargas.

Comparado con `grafo/_data/grafo_urbano.json.gz` (`_meta`, generado
2026-09-09T18:13:43): ese snapshot tiene 27 `EstacionMedida` menos
(4840 vs 4867 real) — el desglose por tipo aísla la diferencia por
completo en `trafico` (4678 en el snapshot vs **4705** real; `aforos`,
`ruido`, `meteo`, `calidad_aire` coinciden exactamente). Esto **no es un
bug**: el propio `VIC_34` (este ticket) y `FIL_66` ya asumen 4705 puntos
de tráfico como la cifra correcta (ver punto 3) — es el fichero
`grafo_urbano.json.gz` el que quedó una carga por detrás. Ese snapshot es
la fuente offline que usan `modelado/grafo_analitica/` (`VIC_36`/`VIC_41`
ya lo verificaron así) y `viz/`, así que ambos análisis son
**autoconsistentes entre sí pero 27 nodos de tráfico por detrás de la
instancia real** — sin impacto en las conclusiones de resiliencia/
centralidad (27 de 1798 nodos del subgrafo de tráfico con coordenadas es
ruido estadístico), pero vale la pena regenerarlo antes de la entrega para
que el snapshot y la instancia real no diverjan más. Anotado, sin ticket
nuevo (es un `regenerar y versionar de nuevo`, no un bug de lógica —
mismo patrón que `tasks/FIL_51`/`FIL_65`).

## 2. Idempotencia / huérfanos — ✅ sin duplicados; aislamiento explicado

- **0 nodos con `id` duplicado** (`MATCH (n) ... WITH n.id, count(*) AS c
  WHERE c > 1` → 0 filas).
- **"Aristas `PROXIMO_A` a un id inexistente"**: estructuralmente
  imposible en el modelo de grafo de propiedades de Neo4j — una relación
  siempre conecta dos nodos ya existentes en el momento de crearla (no es
  una clave foránea que pueda apuntar a un id ausente). Confirmado además
  de forma indirecta: `id`/`tipo`/`fuente` aparecen como `mandatory: true`
  en `db.schema.nodeTypeProperties()` para los 3 labels espaciales — no
  hay nodos "stub" (creados solo por un `MERGE` de relación sin sus
  propiedades reales).
- **Nodos aislados** (sin `UBICADO_EN` ni `PROXIMO_A`, patrón no
  dirigido): 86 `ParadaTransporte` + 10 `Lugar`. Investigado uno a uno:
  - Los 10 `Lugar` son POIs turísticos/recintos/cines **fuera del
    municipio de Madrid** (Monasterio de El Escorial, El Cerro de los
    Ángeles, Alcalá de Henares, Arganda del Rey...) — `UBICADO_EN` solo
    resuelve contra los 131 barrios del municipio, y no hay sensor a
    &lt;300 m en sitios así de alejados. Comportamiento esperado, no un bug.
  - De los 86 `ParadaTransporte`, 21 están **totalmente** aislados (ni
    siquiera `CONECTADO_CON`): 20 son paradas BiciMAD con `ubicacion`
    real pero en municipios periféricos (nombres como "POZUELO ESTACIÓN",
    fuera de los 21 distritos de Madrid capital) y 1 es
    `transporte_publico_emt:71`, la única parada EMT capturada
    (limitación conocida de `FIL_07`, sin líneas para tejer
    `CONECTADO_CON`). Los 65 restantes (86-21) sí tienen `CONECTADO_CON`
    (pertenecen a una línea) pero no un ancla espacial — mismo patrón,
    paradas BiciMAD/EMT sin barrio de Madrid capital ni sensor cercano.
  - Nada de esto es un huérfano real: todos tienen datos válidos, solo
    están geográficamente fuera del alcance de `UBICADO_EN`/`PROXIMO_A`
    (limitados a Madrid capital y a un radio de 300 m).

## 3. Cobertura de atributos FIL_66 — ✅ los 5 coinciden exactamente

| Atributo | Total | Con dato | Esperado (ticket) |
|---|---|---|---|
| `contaminantes` (calidad_aire) | 23 | 23 | 23/23 ✓ |
| `magnitudes` (meteo) | 25 | 25 | 25/25 ✓ |
| `subarea` (trafico) | 4705 | 4413 | 4413/4705 ✓ |
| `anclajes_totales` (bicimad) | 680 | 680 | 680/680 ✓ |
| `plazas_totales` (aparcamiento) | 26 | 22 | 22/26 ✓ |

- **`subarea`**: confirmado en código, no solo asumido — `grafo/extract.py`
  aplica `_recent_date_filter()` (ventana de 14 días) a la consulta de
  `subarea`; los 292 puntos sin dato son tráfico que no reportó en esa
  ventana, no un fallo del `JOIN`.
- **`plazas_totales`**: verificado con una consulta Athena real y
  específica (no solo aceptado el número) — `parking_id` 92, 91, 81 y 84
  tienen `total_spaces = NULL` en `gold.aparcamientos_por_parking_hora`
  para su última fecha (`2026-08-30`, coherente con el pipeline
  congelado). Es un null real en Gold, no un artefacto de ventana — los 22
  restantes sí tienen valor en esa misma fecha.

## 4. `nombre` (FIL_67) — ✅ exacto: 162/162

| Tipo | Total | Con nombre |
|---|---|---|
| aforos_peatones_bicicletas | 83 | 83 |
| calidad_aire | 23 | 23 |
| meteo | 25 | 25 |
| ruido | 31 | 31 |
| trafico | 4705 | **0** (por diseño) |

83+23+25+31 = **162**, exactamente la cifra esperada. Ninguna estación con
nombre en Gold se quedó sin él en el grafo.

## 5. meteo / recinto — ✅ exacto en meteo; recinto con un dato adicional

- **meteo**: 25 total, 25/25 `UBICADO_EN`, **24/25** `PROXIMO_A` — exacto.
  La estación sin `PROXIMO_A` es `meteorologia:28079104` ("E.D.A.R. La
  China", una depuradora), consistente con "1 periférica".
- **recinto**: 145 total, **142/145** `PROXIMO_A` — exacto. Los 3 sin
  `PROXIMO_A`: "Centro Deportivo Alcalá de Henares", "Estadio Ontime
  Butarque" (ambos fuera del municipio de Madrid) e "Iberdrola Music" (sí
  está en Madrid pero a &gt;300 m de cualquier sensor — un dato nuevo que el
  ticket no había anticipado explícitamente, pero mismo patrón). Dato
  adicional no pedido por el ticket: de los 145, **142/145** tienen
  también `UBICADO_EN` — los 3 sin él son los 2 recintos fuera de Madrid
  más "Iberdrola Music" pese a tener `PROXIMO_A`... corrección: los que
  faltan `UBICADO_EN` son exactamente los 2 fuera de Madrid capital (el
  tercero, con `PROXIMO_A`, sí cae dentro de un barrio). Sin bug: mismo
  criterio geográfico que el punto 2.

Nota metodológica: `count { patrón }` combinado con `count(n)` en la misma
cláusula `RETURN` de Cypher (Neo4j 5) da resultados por-fila en vez de un
agregado único cuando se mezclan así — hay que separarlos en consultas
independientes (`MATCH ... RETURN count(...)`) para un total limpio. Y
`PROXIMO_A` se recorre con patrón **no dirigido** (`-[:PROXIMO_A]-`, sin
flecha) porque el sentido de la relación no es predecible por tipo de
nodo — ya lo advierte `schema.cypher` línea 166.

## 6. `schema.cypher` ↔ esquema vivo — ✅ coinciden

- **Constraints** (5, todas `NODE_PROPERTY_UNIQUENESS` sobre `id`/`codigo`
  según el label): `barrio_codigo_unique`, `distrito_codigo_unique`,
  `estacion_medida_id_unique`, `lugar_id_unique`,
  `parada_transporte_id_unique` — coinciden 1:1 con lo documentado.
- **Índices**: además de los 5 de unicidad, existen índices `RANGE` sobre
  `tipo` (EstacionMedida/Lugar/ParadaTransporte) y `POINT` sobre
  `ubicacion` (los 3 mismos labels) — documentados en `schema.cypher`
  líneas 116/119 y equivalentes.
- **Propiedades por nodo** (`db.schema.nodeTypeProperties()`):
  `EstacionMedida` real = `id, tipo, fuente, ubicacion` (obligatorias) +
  `nombre, subarea, contaminantes, altitud_m, modos, magnitudes`
  (opcionales) — las 10 están documentadas en `schema.cypher`
  (líneas 98-109). `Lugar` real añade `plazas_totales` (línea 74) y
  `ParadaTransporte` añade `anclajes_totales` (línea 132) — ambas
  documentadas. Sin propiedades huérfanas ni sin documentar.

## Cifras finales del grafo (para `VIC_38` / capítulo de grafo)

**5 labels, 9806 nodos, 4 tipos de relación, 76002 relaciones:**

| Label | n |
|---|---|
| EstacionMedida | 4867 (trafico 4705, aforos 83, ruido 31, meteo 25, calidad_aire 23) |
| ParadaTransporte | 4056 |
| Lugar | 731 (poi_turistico 355, parque 203, recinto 145, aparcamiento 26, cine 2) |
| Barrio | 131 |
| Distrito | 21 |

| Relación | n |
|---|---|
| PROXIMO_A | 54380 |
| CONECTADO_CON | 11998 |
| UBICADO_EN | 9493 |
| PERTENECE_A | 131 |

Qué añadió cada ticket: `FIL_65` incorporó los 25 nodos `meteo` y 145
`recinto` (antes ausentes del grafo); `FIL_66` añadió 5 atributos
estáticos por tipo de entidad (contaminantes/magnitudes/subarea/
anclajes_totales/plazas_totales), leídos de Gold sin reingesta;
`FIL_67` persistió `nombre` en 162 estaciones (antes solo vivía en Gold).

## Veredicto

Los 6 puntos verifican limpio contra la instancia real de hoy. Un único
hallazgo no-bloqueante: `grafo/_data/grafo_urbano.json.gz` (snapshot
offline usado por `modelado/grafo_analitica/` y `viz/`) va 27 nodos de
tráfico por detrás de la instancia real — cosmético para este trabajo,
pero conviene regenerarlo (`python -m grafo.extract` + lo que exporte a
ese fichero) antes de la entrega para que deje de divergir. No se abre
ticket `FIL_*` nuevo — es una tarea de "regenerar artefacto", no un
defecto de lógica, y ya está anotada aquí para quien la recoja.
