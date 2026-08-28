# 094 — QA: recargar el grafo real con OSM/aforos, y un hallazgo real más grave por el camino

## Contexto

`madrono-agent` encoló esta tarea de QA tras detectar que la instancia
real de Neo4j seguía teniendo exactamente los mismos conteos de nodos que
`doc/080` (24/8), pese a que las tareas 083 (enriquecimiento OSM) y 087
(nodos de aforos) ya estaban marcadas como completadas — ambas ya admitían
en su propio `doc/` que no habían recargado la instancia real. El intento
automático del demonio terminó en `status: failed` (`last_error: claude
finalizó sin crear ningún commit`) sin ningún hallazgo documentado. Se
retoma aquí de forma interactiva, con acceso real a AWS/Neo4j.

## Antes de tocar nada: verificación de partida (Cypher real)

```
MATCH (n) RETURN labels(n)[0], count(n)
EstacionMedida  4740
ParadaTransporte 4056
Lugar            381
Barrio           131
Distrito          21
```

```
MATCH (l:Lugar) WHERE l.osm_id IS NOT NULL RETURN count(l)   → 0
MATCH (e:EstacionMedida {tipo: 'aforos_peatones_bicicletas'}) RETURN count(e)  → 0
```

Confirma exactamente lo que reportaba el ticket del demonio.

## Primer intento: `python3 -m grafo.cargar_grafo` real -- cuelgue de 3 horas

Lanzado con las credenciales de Neo4j reales (SSM) y la cuenta AWS del
proyecto. El proceso se dejó correr en segundo plano; el seguimiento
inicial (por tiempo de CPU acumulado, que crecía de forma modesta y
aparentemente sana) fue **engañoso** -- el tiempo de CPU no revela un
proceso mayormente bloqueado esperando red/servidor. Al comparar tiempo de
CPU contra tiempo de reloj real se descubrió la magnitud real del
problema:

- Tiempo de reloj transcurrido: **~2h 55min**.
- Tiempo de CPU real acumulado: **96 segundos** (~0.9% de utilización).

`SHOW TRANSACTIONS` contra la instancia real confirmó qué estaba
ejecutando en ese momento:

```cypher
MATCH (a {id: $origen_id}), (b {id: $destino_id})
MERGE (a)-[r:PROXIMO_A]->(b) SET r.distancia_m = $distancia_m
```

## Causa raíz: `infra/neo4j/schema/schema.cypher` nunca se aplicó a la instancia real

`SHOW CONSTRAINTS` contra la instancia real devolvió **una lista vacía**.
Solo existían los 2 índices `LOOKUP` que Neo4j crea automáticamente por
label/tipo de relación -- ninguno de los constraints `..._id_unique`/
`..._codigo_unique` que `schema.cypher` define para `:Distrito`/`:Barrio`/
`:Lugar`/`:EstacionMedida`/`:ParadaTransporte` (tarea 043) estaba aplicado.

`infra/neo4j/README.md` ya documentaba el paso como parte del alta de una
instancia real (`cypher-shell ... -f infra/neo4j/schema/schema.cypher`,
paso 4 de 4) -- pero, según el propio README, "Ninguno de estos 4 pasos se
ha completado en esta tarea" se escribió cuando la instancia **todavía no
existía** (tarea 043). Cuando la tarea 080 creó la instancia real y cargó
los primeros datos, ese paso 4 se quedó sin ejecutar, y **no falló de
forma visible en ese momento**: sobre una base de datos vacía, `MERGE (n
{id: $id})` sin índice es barato (no hay nada que escanear todavía). El
problema solo se manifiesta al recargar un grafo **ya poblado** con miles
de nodos: cada `MATCH`/`MERGE` sin índice sobre una propiedad se convierte
en un escaneo completo de todos los nodos existentes de ese tipo. Con
`relaciones.proximo_a` generando del orden de decenas de miles de pares
`(origen_id, destino_id)`, cada uno con un escaneo completo sobre miles de
nodos existentes, el coste real es varios órdenes de magnitud mayor que
"O(n²) en Python" (que sí es barato) -- es O(n²) llamadas × O(n) escaneo
servidor, no detectado hasta esta tarea porque nadie había vuelto a
ejecutar una recarga completa contra el grafo ya poblado desde la tarea
080.

**Se detuvo el proceso colgado** (`Stop-Process`) en vez de esperar a que
terminara solo -- no había ninguna garantía de que fuera a terminar en
tiempo razonable, y cada `MERGE`/`MATCH` es una operación independiente
(no una única transacción larga), así que interrumpir el cliente no deja
ningún dato a medio escribir ni corrompe nada, solo detiene el envío de
más peticiones.

## Arreglo: aplicar `schema.cypher` contra la instancia real

Las 12 sentencias de `infra/neo4j/schema/schema.cypher` (3 `CREATE
CONSTRAINT` + 9 `CREATE INDEX`/`CREATE POINT INDEX`, todas `IF NOT
EXISTS`) se ejecutaron una a una vía el driver `neo4j` de Python
(`cypher-shell` no está instalado en este entorno) contra la instancia
real. Es una operación puramente aditiva y segura: no modifica ni borra
ningún dato existente, es idempotente por diseño, y es exactamente el paso
que la documentación del proyecto ya decía que hacía falta. Verificado
después con `SHOW CONSTRAINTS`/`SHOW INDEXES`: las 5 constraints y los 9
índices de propiedad/punto (más los 2 `LOOKUP` automáticos) quedaron
`ONLINE`.

## Segundo intento: recarga real completa, ~20 minutos, sin errores

Con los índices ya aplicados, se relanzó `python3 -m grafo.cargar_grafo`.
Verificado en directo con `SHOW TRANSACTIONS` que la misma consulta
`UBICADO_EN` que antes tardaba minutos por llamada ahora completaba en
**2-5 milisegundos**. El tiempo total (~20 minutos) no viene ya de la base
de datos, sino de dos factores reales y acotados, no de otro cuelgue:

1. Cada nodo/relación se escribe con su propia llamada `session.run()`
   secuencial (`grafo/cypher.py::_run_all`, mismo patrón sin `UNWIND` para
   los 9 tipos de carga) -- miles de idas y vueltas de red individuales al
   free tier de AuraDB, cada una rápida pero no gratis en conjunto.
2. `relaciones.ubicado_en()` calcula, en Python puro y por adelantado
   (antes de escribir nada), un point-in-polygon real contra los ~131
   barrios para cada uno de los ~9000 nodos con ubicación -- cómputo
   legítimo, acotado (no crece con el tamaño del grafo, a diferencia del
   bug de arriba), pero no trivial.

### Resultado final, verificado con Cypher real (no con tests)

```
MATCH (n) RETURN labels(n)[0], count(n)
Barrio            131
Distrito           21
EstacionMedida   4755
Lugar             383
ParadaTransporte 4056

MATCH ()-[r]->() RETURN type(r), count(r)
PERTENECE_A        131
UBICADO_EN        9038
PROXIMO_A        46037
CONECTADO_CON    11998
```

Total ≈ 9346 nodos / 67204 relaciones -- del mismo orden que los "9327
nodos / 67158 relaciones" que `doc/080` reportó el 24/8, con crecimiento
orgánico esperable (más estaciones/lugares reales capturados desde
entonces).

- **OSM (tarea 083)**: `MATCH (l:Lugar) WHERE l.osm_id IS NOT NULL RETURN
  count(l)` → **0**. No es un fallo: la muestra committeada de POIs de OSM
  tiene solo 6 puntos fijos (`doc/083`, "Cobertura real limitada a 6 POIs
  de muestra"), y ninguno de los 383 `:Lugar` reales cae a ≤30m de
  ninguno de esos 6 puntos. El código de enriquecimiento se ejecutó sin
  errores; el bloqueo real es la falta de una captura completa de OSM
  (trabajo futuro ya señalado en `doc/083`).
- **Aforos (tarea 087)**: `MATCH (e:EstacionMedida {tipo:
  "aforos_peatones_bicicletas"}) RETURN count(e)` → **0**. Tampoco es un
  fallo nuevo: sigue bloqueado por el mismo problema de partition
  projection en Athena ya diagnosticado (`doc/087`/`doc/090`), cuyo fix ya
  está escrito en `infra/terraform/glue.tf` pero sin `apply` (Prioridad
  1/2 de `NEXT_STEPS.md`).

## Actualización 28/8 — recarga rerun tras la tarea 098; un segundo bloqueador de aforos, arreglado

La tarea 098 (26/8) aplicó el `terraform apply` que desbloqueó el Gold de
`aforos_peatones_bicicletas` en Athena (1971 filas reales, antes 0). Pero
**nadie relanzó `cargar_grafo.py` después**, así que la instancia real
seguía con 0 nodos de aforos. Al relanzarlo hoy (28/8, con credenciales
AWS `AWS_PROFILE=madrono` + Neo4j de SSM) se encontró un **segundo
bloqueador**, distinto del de partition projection:

`grafo/extract.py::fetch_estaciones_aforos_peatones_bicicletas()` aplicaba
`_recent_date_filter()` (últimos 14 días), igual que las funciones de
`trafico`/`calidad_aire`/`ruido`. Pero la fuente de aforos está **congelada
en 2024-06-30** — las 1971 filas de Gold tienen todas `date = "2024-06-30"`,
así que el filtro "últimos 14 días" dejaba la consulta en **0 filas** y los
nodos nunca entraban al grafo, aunque la tabla ya tuviera datos.

**Arreglo** (`grafo/extract.py`): quitar `_recent_date_filter()` solo de esa
función. La tabla entera son ~2000 filas (fuente descontinuada), así que
escanearla completa para quedarse con la última ubicación conocida por
estación (`max_by(col, date)`) es correcto y barato. Los 93 tests de
`grafo/` siguen en verde (el `test_extract.py` de aforos no comprueba el
SQL, solo el parseo).

### Resultado final, verificado con Cypher real (28/8)

```
MATCH (e:EstacionMedida) RETURN e.tipo, count(e)
  aforos_peatones_bicicletas  83     (antes 0)
  calidad_aire                23
  ruido                       31
  trafico                     4702

MATCH (n) RETURN count(n)              → 9530   (antes ~9346)
MATCH ()-[r:PROXIMO_A]->() RETURN count(r) → 48024  (antes 46037; +1987 de la proximidad de aforos)
MATCH (e:EstacionMedida {tipo:'aforos_peatones_bicicletas'})-[:PROXIMO_A]-(l:Lugar)
  RETURN count(DISTINCT e)             → 38     (aforos con un :Lugar cercano)
```

- **OSM sigue en 0** — mismo motivo que arriba (muestra de 6 POIs). Sin
  cambios; el fix real es una captura Overpass completa (trabajo futuro,
  `doc/083`).
- La recarga tardó ~51 min (vs ~20 la anterior) — free tier de AuraDB más
  lento hoy; no hubo cuelgue, los conteos avanzaron de forma monótona todo
  el rato. `MERGE` idempotente, sin pérdida ni corrupción.
- Único efecto real: 83 nodos nuevos + sus relaciones. No se tocó
  `infra/terraform/` ni se aplicó nada en AWS (el fix es solo Python).

## Restricciones respetadas

- Ninguna credencial de Neo4j se ha escrito en el repositorio -- leídas de
  SSM en memoria en cada script de verificación/carga, nunca a disco.
- No se ha tocado `infra/terraform/` ni ejecutado ningún `terraform
  apply`/`aws` con efectos reales -- el problema de aforos sigue
  bloqueado, tal como anticipaba el enunciado de esta tarea, documentado
  en vez de forzado con datos falsos.
- El único cambio de infraestructura real de esta tarea es la aplicación
  de `schema.cypher` (constraints/índices) contra Neo4j -- puramente
  aditivo, sin tocar ni borrar ningún dato existente.
- El proceso colgado se detuvo de forma segura (operaciones independientes,
  no una transacción larga) en vez de dejarlo corriendo indefinidamente.

## Relevante para tareas futuras

- **Cualquier recarga futura de `grafo.cargar_grafo` ya no tiene el riesgo
  de cuelgue** -- los índices están aplicados. Si se vuelve a observar una
  recarga anormalmente lenta, comprobar primero `SHOW CONSTRAINTS`/`SHOW
  INDEXES` contra la instancia real antes de asumir que es un problema del
  código Python.
- `infra/neo4j/schema/schema.cypher` debería ejecutarse como parte
  estándar de cualquier futura recreación de la instancia (p.ej. si se
  migra de AuraDB Free a otra instancia) -- no asumir que "ya se aplicó
  una vez" es suficiente sin comprobarlo primero, como demostró esta
  tarea.
- Cobertura real de OSM sigue limitada a 6 POIs de muestra -- una captura
  completa (todo Madrid, por distrito para respuestas manejables) es el
  siguiente paso natural si se quiere que el enriquecimiento produzca
  resultados reales, no solo código correcto sin datos que enriquecer.
- Aforos de peatones/bicicletas sigue bloqueado por Terraform sin aplicar
  -- ver Prioridad 1/2 de `NEXT_STEPS.md`.
